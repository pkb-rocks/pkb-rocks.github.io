"""Expose only the configured PIN-less PIV bot key to standard OpenSSH tools."""
import argparse
from contextlib import contextmanager
import base64
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import tempfile

# User-local Fedora packages; no private key material is loaded from disk.
TOOL_ROOT = Path.home() / '.local/share/agent-tools/yubico-piv-tool/root/usr'
version = f'python{sys.version_info.major}.{sys.version_info.minor}'
for path in (TOOL_ROOT / f'lib/{version}/site-packages', TOOL_ROOT / f'lib64/{version}/site-packages'):
    if path.is_dir():
        sys.path.insert(0, str(path))

MAX_MESSAGE = 1024 * 1024


def string(value):
    return struct.pack('>I', len(value)) + value


def read_string(data):
    if len(data) < 4:
        raise ValueError('Truncated SSH string')
    length = struct.unpack('>I', data[:4])[0]
    if length > len(data) - 4:
        raise ValueError('Truncated SSH string')
    return data[4:4 + length], data[4 + length:]


def load_config(path):
    config = json.loads(path.read_text())
    if (config['account'], config['email'], config['serial'], config['slot']) != (
            'pkb-rocks-bot', 'bot@pkb.rocks', 38906327, '9a'):
        raise RuntimeError('Unexpected bot identity or YubiKey slot in configuration.')
    key = Path(config['public_key']).expanduser()
    if not key.is_absolute():
        key = path.parent / key
    config['public_key'] = str(key.resolve())
    parts = key.read_bytes().split()
    if len(parts) < 2 or parts[0] != b'ecdsa-sha2-nistp256':
        raise RuntimeError('Expected a P-256 SSH public key.')
    config['allowed_signers'] = str(path.parent / 'allowed-signers')
    config['ssh_config'] = str(path.parent / 'ssh_config')
    config['blob'] = base64.b64decode(parts[1], validate=True)
    return config


class PivSigner:
    def __init__(self, config):
        self.config = config
        self.check()

    @contextmanager
    def session(self):
        from ykman.device import list_all_devices
        from yubikit.core.smartcard import SmartCardConnection
        from yubikit.piv import PivSession, SLOT, PIN_POLICY, TOUCH_POLICY
        devices = [device for device, info in list_all_devices() if info.serial == self.config['serial']]
        if len(devices) != 1:
            raise RuntimeError('The configured bot YubiKey is unavailable.')
        with devices[0].open_connection(SmartCardConnection) as connection:
            session = PivSession(connection)
            metadata = session.get_slot_metadata(SLOT.AUTHENTICATION)
            from cryptography.hazmat.primitives import serialization
            public = metadata.public_key.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
            blob = base64.b64decode(public.split()[1])
            if (session.get_serial() != self.config['serial'] or blob != self.config['blob']
                    or not metadata.generated or metadata.pin_policy != PIN_POLICY.NEVER
                    or metadata.touch_policy != TOUCH_POLICY.NEVER):
                raise RuntimeError('Bot key identity or PIN/touch policy does not match.')
            yield session

    def check(self):
        with self.session():
            pass

    def __call__(self, data):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        from yubikit.piv import SLOT, KEY_TYPE
        with self.session() as session:
            der = session.sign(SLOT.AUTHENTICATION, KEY_TYPE.ECCP256, data, hashes.SHA256())
        r, s = decode_dss_signature(der)
        def mpint(value):
            raw = value.to_bytes((value.bit_length() + 7) // 8, 'big')
            if raw and raw[0] & 0x80:
                raw = b'\0' + raw
            return string(raw)
        return string(b'ecdsa-sha2-nistp256') + string(mpint(r) + mpint(s))


def response(message, public_blob, signer):
    if message == b'\x0b':  # SSH_AGENTC_REQUEST_IDENTITIES
        return b'\x0c' + struct.pack('>I', 1) + string(public_blob) + string(b'PKB.rocks Bot / YK2 / PIV 9a')
    if message[:1] == b'\x0d':  # SSH_AGENTC_SIGN_REQUEST
        key, rest = read_string(message[1:])
        data, flags = read_string(rest)
        if key == public_blob and flags == b'\0\0\0\0':
            return b'\x0e' + string(signer(data))
    return b'\x05'  # SSH_AGENT_FAILURE; key import, PIN operations and extensions unsupported.


def receive(connection, count):
    chunks = bytearray()
    while len(chunks) < count:
        data = connection.recv(count - len(chunks))
        if not data:
            raise EOFError
        chunks.extend(data)
    return bytes(chunks)


def serve(path, public_blob, signer):
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(str(path))
        path.chmod(0o600)
        server.listen(4)
        print('READY', flush=True)
        while True:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(15)
                try:
                    while True:
                        length = struct.unpack('>I', receive(connection, 4))[0]
                        if length > MAX_MESSAGE:
                            raise ValueError('SSH agent message too large')
                        result = response(receive(connection, length), public_blob, signer)
                        connection.sendall(string(result))
                except (EOFError, BrokenPipeError, ConnectionResetError, TimeoutError):
                    pass
                except Exception as error:
                    print(f'Bot agent request failed: {type(error).__name__}', file=sys.stderr)
                    try:
                        connection.sendall(string(b'\x05'))
                    except OSError:
                        pass


@contextmanager
def bot_agent(config_path, state):
    config = load_config(config_path)
    with tempfile.TemporaryDirectory(prefix='bot-agent-', dir=state) as directory:
        socket_path = Path(directory) / 'agent.sock'
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
            '--config', str(config_path), '--socket', str(socket_path)], stdout=subprocess.PIPE, text=True)
        try:
            ready, _, _ = select.select([process.stdout], [], [], 20)
            if not ready or process.stdout.readline().strip() != 'READY':
                raise RuntimeError('The PIV bot agent could not start; publication is disabled.')
            env = dict(os.environ, SSH_AUTH_SOCK=str(socket_path), GIT_TERMINAL_PROMPT='0')
            import shlex
            env['GIT_SSH_COMMAND'] = 'ssh -F ' + shlex.quote(config['ssh_config'])
            env.pop('GIT_SSH', None)
            for prefix in ('GIT_AUTHOR_', 'GIT_COMMITTER_'):
                for field in ('NAME', 'EMAIL'):
                    env[prefix + field] = config['name'] if field == 'NAME' else config['email']
            yield config, env
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdout.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path,
                        default=Path.home() / '.config/plektra-stats/bot.json')
    parser.add_argument('--socket', type=Path)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.socket:
        config = load_config(args.config)
        serve(args.socket, config['blob'], PivSigner(config))
    else:
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not command:
            parser.error('Provide a command after --, or an agent socket path.')
        state = Path.home() / '.local/state/plektra-stats'
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        with bot_agent(args.config.resolve(), state) as (_, env):
            sys.exit(subprocess.run(command, env=env).returncode)
