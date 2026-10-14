"""Check local deadline gating without contacting GitHub or publishing."""
from datetime import datetime, timezone, timedelta
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import piv_bot

spec = importlib.util.spec_from_file_location('runner', Path(__file__).parents[1] / 'run-release-stats.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerScheduleTests(unittest.TestCase):
    def test_next_collection_is_due_at_its_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'next-run.json'
            target = datetime(2026, 10, 15, 18, 59, 43, tzinfo=timezone.utc)
            self.assertTrue(runner.due(marker, target))
            marker.write_text(json.dumps({'next_collection_at': target.isoformat()}))
            self.assertFalse(runner.due(marker, target - timedelta(seconds=1)))
            self.assertTrue(runner.due(marker, target))


    def test_failed_run_backs_off_without_marking_daily_work_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'next-run.json'
            marker.write_text(json.dumps({'next_daily_at':'2026-10-15T03:17:00Z'}))
            now=datetime(2026,10,15,4,0,1,tzinfo=timezone.utc)
            with patch.object(sys,'argv',['runner','--state-dir',directory,'--force']), \
                 patch.object(runner,'execute',side_effect=RuntimeError('hardware unavailable')), \
                 patch.object(runner,'datetime') as clock:
                clock.now.return_value=now
                with self.assertRaisesRegex(RuntimeError,'hardware unavailable'):
                    runner.main()
            result=json.loads(marker.read_text())
            self.assertEqual('2026-10-15T04:05:00Z',result['next_collection_at'])
            self.assertEqual('2026-10-15T03:17:00Z',result['next_daily_at'])


class RunnerPublicationTests(unittest.TestCase):
    def test_preview_and_failed_publication_leave_worktrees_clean(self):
        import subprocess
        import sys
        def command(*args):
            return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout.strip()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, repo, state = root/'remote.git', root/'repo', root/'state'
            command('git', 'init', '--bare', str(remote))
            command('git', 'init', str(repo))
            command('git', '-C', str(repo), 'config', 'user.name', 'Test')
            command('git', '-C', str(repo), 'config', 'user.email', 'test@example.org')
            for name in runner.FILES:
                (repo/name).write_text('{}' if name.endswith('.json') else '<svg/>')
            seed={'schema_version':1,'repository':'pkb-rocks/plektra','releases':[],
                  'last_checked_at':'2026-10-15T12:00:00Z','next_measurement_at':None}
            (repo/'release-stats.json').write_text(json.dumps(seed))
            command('git', '-C', str(repo), 'add', '.')
            command('git', '-C', str(repo), 'commit', '-m', 'Seed')
            command('git', '-C', str(repo), 'remote', 'add', 'origin', str(remote))
            command('git', '-C', str(repo), 'push', 'origin', 'HEAD:stats')
            before = command('git', '--git-dir', str(remote), 'rev-parse', 'stats')
            scripts = repo/'scripts'
            scripts.mkdir()
            # Synthetic collectors keep this test offline and deterministic.
            (scripts/'collect-release-stats.py').write_text('''import pathlib,sys,json
p=pathlib.Path(sys.argv[sys.argv.index('--output')+1]);p.write_text(json.dumps({'next_collection_at':'2099-01-01T00:00:00Z','count':42}))
for n in ('nightly-downloads.svg','stable-downloads.svg'):(p.parent/n).write_text('<svg>updated</svg>')
''')
            (scripts/'collect-star-history.py').write_text('''import pathlib,sys
p=pathlib.Path(sys.argv[-1]);(p/'star-history.json').write_text('{}')
for n in ('star-history.svg','star-history-dark.svg'):(p/n).write_text('<svg>updated</svg>')
''')
            invocation = ['run-release-stats.py', '--repo', str(repo), '--state-dir', str(state), '--force', '--no-push']
            with patch.object(sys, 'argv', invocation), patch.object(runner, 'PUBLIC_REPO', str(remote)), \
                 patch.object(runner, 'bot_agent') as agent, \
                 patch.object(runner.release_collector,'collect',return_value=seed):
                runner.main()
                agent.assert_not_called()
            tree = state/'stats'
            self.assertEqual(before, command('git','--git-dir',str(remote),'rev-parse','stats'))
            self.assertTrue((state/'preview/release-stats.json').exists())
            self.assertEqual(before, command('git','-C',str(tree),'rev-parse','HEAD'))
            stage=state/'preview'
            key=root/'test-key'
            config={'public_key':str(key), 'allowed_signers':str(root/'allowed')}
            import os
            env=dict(os.environ, GIT_AUTHOR_NAME='PKB.rocks Bot', GIT_AUTHOR_EMAIL='bot@pkb.rocks',
                     GIT_COMMITTER_NAME='PKB.rocks Bot', GIT_COMMITTER_EMAIL='bot@pkb.rocks')
            with self.assertRaises(subprocess.CalledProcessError):
                runner.publish(tree,stage,config,env)
            self.assertEqual('', command('git','-C',str(tree),'status','--porcelain'))
            command('ssh-keygen','-q','-t','ed25519','-N','','-f',str(key))
            (root/'allowed').write_text('bot@pkb.rocks '+key.with_suffix('.pub').read_text())
            hook=remote/'hooks/pre-receive'
            hook.write_text('#!/bin/sh\nexit 1\n');hook.chmod(0o755)
            with self.assertRaises(subprocess.CalledProcessError):
                runner.publish(tree,stage,config,env)
            self.assertEqual(before, command('git','--git-dir',str(remote),'rev-parse','stats'))
            self.assertEqual('', command('git','-C',str(tree),'status','--porcelain'))
            hook.unlink()
            runner.publish(tree,stage,config,env)
            after=command('git','--git-dir',str(remote),'rev-parse','stats')
            self.assertNotEqual(before,after)
            self.assertIn('BEGIN SSH SIGNATURE',command('git','--git-dir',str(remote),'cat-file','commit',after))
            self.assertEqual('PKB.rocks Bot <bot@pkb.rocks>',command('git','--git-dir',str(remote),'show','-s','--format=%an <%ae>',after))
            self.assertEqual(before,command('git','-C',str(tree),'rev-parse','HEAD'))
            self.assertEqual('', command('git','-C',str(tree),'status','--porcelain'))


class RunnerDurabilityTests(unittest.TestCase):
    def test_measurement_is_saved_before_render_failure_and_reused_after_restart(self):
        from types import SimpleNamespace
        from test_release_stats import stats, START, empty, release
        published=stats.update(empty(),[release(10)],START+timedelta(hours=20))
        published['next_publication_at']='2026-10-03T03:17:00Z'
        measured=stats.update(published,[release(100)],START+timedelta(hours=24))
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);tree=state/'stats';tree.mkdir()
            (tree/'release-stats.json').write_text(json.dumps(published))
            args=SimpleNamespace(no_push=False)
            marker=state/'next-run.json'
            with patch.object(runner,'git',return_value=''), \
                 patch.object(runner.release_collector,'collect',return_value=measured), \
                 patch.object(runner.release_collector,'chart',side_effect=RuntimeError('render failed')), \
                 patch.object(runner,'bot_agent') as agent:
                with self.assertRaisesRegex(RuntimeError,'render failed'):
                    runner.execute(args,Path(directory),state,marker)
                self.assertEqual(measured,json.loads((state/'pending-release-stats.json').read_text()))
                self.assertFalse(marker.exists())
                agent.assert_not_called()
            retried=stats.update(measured,[release(999)],START+timedelta(hours=24,minutes=1))
            with patch.object(runner,'git',return_value=''), \
                 patch.object(runner.release_collector,'collect',return_value=retried) as collect, \
                 patch.object(runner.release_collector,'chart',side_effect=RuntimeError('render failed')):
                with self.assertRaisesRegex(RuntimeError,'render failed'):
                    runner.execute(args,Path(directory),state,marker)
                seed=collect.call_args.args[1]
                self.assertEqual(100,seed['releases'][0]['snapshots']['24h']['assets'][0]['download_count'])

    def test_routine_poll_changes_counts_without_signing_or_running_star_collection(self):
        from types import SimpleNamespace
        from test_release_stats import stats, START, empty, release
        published=stats.update(empty(),[release(10)],START+timedelta(hours=20))
        published['next_publication_at']='2026-10-03T03:17:00Z'
        collected=stats.update(published,[release(20)],START+timedelta(hours=20,minutes=5))
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);tree=state/'stats';tree.mkdir()
            for name in runner.FILES:
                (tree/name).write_text('{}' if name.endswith('.json') else '<svg/>')
            (tree/'release-stats.json').write_text(json.dumps(published))
            marker=state/'next-run.json'
            marker.write_text(json.dumps({'next_daily_at':'2026-10-03T03:17:00Z'}))
            with patch.object(runner,'git',return_value=''), \
                 patch.object(runner.release_collector,'collect',return_value=collected), \
                 patch.object(runner,'run') as external, patch.object(runner,'bot_agent') as agent:
                runner.execute(SimpleNamespace(no_push=False),Path(directory),state,marker)
                external.assert_not_called();agent.assert_not_called()
            self.assertEqual(20,json.loads((state/'pending-release-stats.json').read_text())['releases'][0]['current']['assets'][0]['download_count'])
            self.assertIn('next_collection_at',json.loads(marker.read_text()))


    def test_failed_star_api_does_not_block_new_release_publication(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from test_release_stats import stats, START, empty, release
        import subprocess
        published=empty();published['next_publication_at']='2026-10-01T03:17:00Z'
        collected=stats.update(published,[release(1)],START)
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);tree=state/'stats';tree.mkdir()
            for name in runner.FILES:
                (tree/name).write_text('{}' if name.endswith('.json') else '<svg/>')
            (tree/'release-stats.json').write_text(json.dumps(published))
            args=SimpleNamespace(no_push=False,bot_config=state/'bot.json')
            marker=state/'next-run.json'
            with patch.object(runner,'git',return_value=''), \
                 patch.object(runner.release_collector,'collect',return_value=collected), \
                 patch.object(runner,'run',side_effect=subprocess.CalledProcessError(1,['collector'])), \
                 patch.object(runner,'bot_agent',return_value=nullcontext(({},{}))), \
                 patch.object(runner,'publish') as publish:
                runner.execute(args,Path(directory),state,marker)
                publish.assert_called_once()
            self.assertEqual('2026-10-02T03:17:00Z',json.loads(marker.read_text())['next_daily_at'])
            self.assertEqual('2026-10-01T12:05:00Z',json.loads(marker.read_text())['next_star_retry_at'])


    def test_star_retries_do_not_republish_download_totals_every_five_minutes(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from test_release_stats import stats, START, empty, release
        import subprocess
        published=stats.update(empty(),[release(10)],START+timedelta(hours=20))
        published['next_publication_at']='2026-10-02T03:17:00Z'
        collected=stats.update(published,[release(20)],START+timedelta(hours=20))
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);tree=state/'stats';tree.mkdir()
            for name in runner.FILES:
                (tree/name).write_text('{}' if name.endswith('.json') else '<svg/>')
            (tree/'release-stats.json').write_text(json.dumps(published))
            args=SimpleNamespace(no_push=False,bot_config=state/'bot.json')
            marker=state/'next-run.json'
            def published_data(tree,stage,*_):
                (tree/'release-stats.json').write_bytes((stage/'release-stats.json').read_bytes())
            with patch.object(runner,'git',return_value=''), \
                 patch.object(runner.release_collector,'collect',return_value=collected), \
                 patch.object(runner,'run',side_effect=subprocess.CalledProcessError(1,['collector'])), \
                 patch.object(runner,'bot_agent',return_value=nullcontext(({},{}))), \
                 patch.object(runner,'publish',side_effect=published_data) as publish:
                runner.execute(args,Path(directory),state,marker)
                publish.assert_called_once()
            retry=stats.update(collected,[release(30)],START+timedelta(hours=20,minutes=5))
            with patch.object(runner,'git',return_value=''), \
                 patch.object(runner.release_collector,'collect',return_value=retry), \
                 patch.object(runner,'run',side_effect=subprocess.CalledProcessError(1,['collector'])), \
                 patch.object(runner,'bot_agent') as agent, patch.object(runner,'publish') as publish:
                runner.execute(args,Path(directory),state,marker)
                publish.assert_not_called();agent.assert_not_called()


class BotAgentProtocolTests(unittest.TestCase):
    def test_only_one_public_key_is_offered(self):
        response=piv_bot.response(b'\x0b',b'configured-key',lambda data: self.fail('Must not sign'))
        self.assertEqual(b'\x0c\0\0\0\1',response[:5])
        key,rest=piv_bot.read_string(response[5:])
        self.assertEqual(b'configured-key',key)
        self.assertIn(b'PIV 9a',rest)

    def test_signing_uses_only_the_exact_key_and_zero_flags(self):
        calls=[]
        def sign(data):
            calls.append(data);return b'signature'
        request=b'\x0d'+piv_bot.string(b'configured-key')+piv_bot.string(b'payload')+b'\0\0\0\0'
        result=piv_bot.response(request,b'configured-key',sign)
        self.assertEqual(b'\x0e'+piv_bot.string(b'signature'),result)
        self.assertEqual([b'payload'],calls)
        self.assertEqual(b'\x05',piv_bot.response(request,b'another-key',sign))
        self.assertEqual(b'\x05',piv_bot.response(request[:-1]+b'\1',b'configured-key',sign))
        self.assertEqual([b'payload'],calls)

    def test_key_import_and_other_operations_are_rejected(self):
        for operation in (b'\x11',b'\x14',b'\x16',b'\x1b',b''):
            self.assertEqual(b'\x05',piv_bot.response(operation,b'key',lambda data:self.fail('Must not sign')))

    def test_truncated_sign_requests_are_rejected(self):
        for message in (b'\x0d',b'\x0d\0\0\0\xff',b'\x0d'+piv_bot.string(b'key')):
            with self.assertRaises(ValueError):
                piv_bot.response(message,b'key',lambda data:self.fail('Must not sign'))

    def test_personal_account_or_other_slot_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'bot.json'
            for slot,account in (('9c','pkb-rocks-bot'),('9a','pzauner')):
                config.write_text(json.dumps({'account':account,'email':'bot@pkb.rocks','serial':38906327,'slot':slot}))
                with self.assertRaisesRegex(RuntimeError,'Unexpected bot identity'):
                    piv_bot.load_config(config)
