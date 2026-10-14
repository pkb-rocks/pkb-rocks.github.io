#!/usr/bin/env python3
"""Enroll the PKB.rocks bot in the empty PIV slot 9a on YubiKey 38906327."""
from datetime import datetime, timedelta, timezone
import base64
import getpass
import hashlib
from pathlib import Path
import sys

# Fedora packages extracted without root into the local tool directory.
tools = Path.home() / '.local/share/agent-tools/yubico-piv-tool/root/usr'
version = f'python{sys.version_info.major}.{sys.version_info.minor}'
for path in (tools / f'lib/{version}/site-packages', tools / f'lib64/{version}/site-packages'):
    sys.path.insert(0, str(path))

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from ykman.device import list_all_devices
from ykman.piv import get_pivman_data, get_pivman_protected_data, generate_self_signed_certificate
from yubikit.core.smartcard import SmartCardConnection, ApduError, SW
from yubikit.piv import PivSession, SLOT, KEY_TYPE, PIN_POLICY, TOUCH_POLICY

SERIAL = 38906327
SLOT_BOT = SLOT.AUTHENTICATION
OUTPUT = Path.home() / '.config/plektra-stats/yubikey'


def main():
    if not sys.stdin.isatty():
        raise RuntimeError('Run this script in your own interactive terminal.')
    devices = [device for device, info in list_all_devices() if info.serial == SERIAL]
    if len(devices) != 1:
        raise RuntimeError(f'Expected exactly one YubiKey with serial {SERIAL}.')
    device = devices[0]
    with device.open_connection(SmartCardConnection) as connection:
        session = PivSession(connection)
        if session.get_serial() != SERIAL:
            raise RuntimeError('Unexpected YubiKey.')
        try:
            session.get_slot_metadata(SLOT_BOT)
        except ApduError as error:
            if error.sw != SW.REFERENCE_DATA_NOT_FOUND:
                raise
        else:
            raise RuntimeError('Slot 9a already contains a key. Nothing was overwritten.')
        if OUTPUT.exists() and any(OUTPUT.iterdir()):
            raise RuntimeError(f'{OUTPUT} is not empty. Nothing was overwritten.')
        before = {slot: session.get_slot_metadata(slot) for slot in (SLOT.SIGNATURE, SLOT.RETIRED1)}
        if not get_pivman_data(session).has_stored_key:
            raise RuntimeError('No PIN-protected management key is recorded. Nothing was changed.')
        print(f'YK2 {SERIAL}: slot 9a is empty; APK slots 9c and 82 will be preserved.')
        print('Creating a new on-device P-256 bot key: PIN Never, Touch Never.')
        pin = getpass.getpass('PIV PIN (hidden; one attempt): ')
        session.verify_pin(pin)
        del pin
        management_key = get_pivman_protected_data(session).key
        if management_key is None:
            raise RuntimeError('Protected management key is missing. Nothing was changed.')
        session.authenticate(management_key)
        del management_key
        OUTPUT.mkdir(parents=True, mode=0o700)
        OUTPUT.chmod(0o700)
        public_key = session.generate_key(SLOT_BOT, KEY_TYPE.ECCP256, PIN_POLICY.NEVER, TOUCH_POLICY.NEVER)
        pem = public_key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        ssh = public_key.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
        (OUTPUT / 'bot-public.pem').write_bytes(pem)
        (OUTPUT / 'bot.pub').write_bytes(ssh + b' bot@pkb.rocks\n')
        metadata = session.get_slot_metadata(SLOT_BOT)
        if not metadata.generated or metadata.pin_policy != PIN_POLICY.NEVER or metadata.touch_policy != TOUCH_POLICY.NEVER:
            raise RuntimeError('New key metadata does not match the requested policy.')
        attestation = session.attest_key(SLOT_BOT)
        if attestation.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo) != pem:
            raise RuntimeError('Attestation public key mismatch.')
        (OUTPUT / 'bot-attestation.pem').write_bytes(attestation.public_bytes(serialization.Encoding.PEM))
        issuer = session.get_certificate(SLOT.ATTESTATION)
        (OUTPUT / 'device-attestation.pem').write_bytes(issuer.public_bytes(serialization.Encoding.PEM))
        now = datetime.now(timezone.utc)
        certificate = generate_self_signed_certificate(session, SLOT_BOT, public_key,
            'CN=PKB.rocks Bot,OU=Automated Git updates,O=PKB.rocks',
            now - timedelta(minutes=5), now + timedelta(days=3650))
        session.put_certificate(SLOT_BOT, certificate)
        (OUTPUT / 'bot-certificate.pem').write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        for slot, expected in before.items():
            if session.get_slot_metadata(slot) != expected:
                raise RuntimeError(f'Unexpected change to existing slot {int(slot):02x}.')
    # A fresh connection demonstrates that no cached PIN authentication is needed.
    with device.open_connection(SmartCardConnection) as connection:
        session = PivSession(connection)
        challenge = b'PKB.rocks bot enrollment check: YK2 slot 9a'
        signature = session.sign(SLOT_BOT, KEY_TYPE.ECCP256, challenge, hashes.SHA256())
        public_key.verify(signature, challenge, ec.ECDSA(hashes.SHA256()))
    fingerprint = base64.b64encode(hashlib.sha256(base64.b64decode(ssh.split()[1])).digest()).decode().rstrip('=')
    print('Done: fresh-session signing passed without PIN or touch; APK slots unchanged.')
    print('SSH fingerprint: SHA256:' + fingerprint)
    print('Public key: ' + str(OUTPUT / 'bot.pub'))
    print((OUTPUT / 'bot.pub').read_text(), end='')
    print('Register this public key twice in pkb-rocks-bot: Authentication Key and Signing Key.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Stopped: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
