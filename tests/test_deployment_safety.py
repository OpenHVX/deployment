"""Exercise failure boundaries without connecting to Windows, K3s or Ceph.

These tests deliberately inspect outcomes: stale files must disappear, changed
bootstrap must fail, failed imports must not publish a release, and failed
rollouts must not reopen admission. Syntax checks alone cannot prove those rules.
"""
import importlib.util
import io
from contextlib import redirect_stdout, redirect_stderr
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lab/scripts'))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'lab/scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


infra = load('infra_safety', 'prepare-infra.py')
sources = load('source_safety', 'image_sources.py')
builder = load('builder_safety', 'build-images.py')
platform = load('platform_safety', 'platform-up.py')


class BootstrapSafetyTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('xorriso'), 'xorriso required for the real ISO contract')
    def test_cached_iso_is_verified_and_changed_network_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            iso = folder / 'seed.iso'
            original = infra.seed_contents('test-vm', '192.0.2.21', 'ssh-ed25519 TEST')
            infra.write_seed(folder / 'sources', iso, original)
            before = iso.read_bytes()
            infra.verify_existing_seed(iso, original)
            # An editable sidecar is not evidence of what the guest actually got.
            (folder / 'sources/network-config').write_text('wrong cache')
            changed = infra.seed_contents('test-vm', '192.0.2.22', 'ssh-ed25519 TEST')
            with self.assertRaisesRegex(ValueError, 'differs'):
                infra.verify_existing_seed(iso, changed)
            self.assertEqual(iso.read_bytes(), before)


class ReleaseSafetyTest(unittest.TestCase):
    def test_equal_sources_receive_distinct_versions_and_exclude_private_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / 'source'
            source.mkdir()
            (source / 'Dockerfile').write_text('FROM scratch\n')
            (source / '.env').write_text('not-for-images')
            with patch.object(sources, 'WORK', folder / 'work'), \
                 patch.object(sources, 'SERVICES', ('auth',)), \
                 patch.object(sources, 'source_directory', return_value=source):
                first_tag, first = sources.prepare_release()
                second_tag, second = sources.prepare_release()
            self.assertNotEqual(first_tag, second_tag)
            self.assertEqual((first / 'source-sha256').read_text(), (second / 'source-sha256').read_text())
            with tarfile.open(first / 'build/auth.tgz') as archive:
                self.assertNotIn('./.env', archive.getnames())

    def test_failed_import_does_not_publish_the_candidate_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / 'image-tag').write_text('previous-release\n')
            with patch.object(builder, 'WORK', work), \
                 patch.object(builder, 'ensure_lab_lock'), \
                 patch.object(builder, 'prepare_release', return_value=('candidate', work)), \
                 patch.object(builder, 'run_playbook', side_effect=RuntimeError('import failed')):
                with self.assertRaisesRegex(RuntimeError, 'import failed'):
                    builder.main()
            self.assertEqual((work / 'image-tag').read_text(), 'previous-release\n')

    def test_build_context_removes_files_absent_from_the_next_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = root / 'release'
            (release / 'build').mkdir(parents=True)
            current = root / 'current.ts'
            current.write_text('current source')
            with tarfile.open(release / 'build/auth.tgz', 'w:gz') as archive:
                archive.add(current, arcname='current.ts')
            tag = 'lab-' + 'a' * 32
            remote_root = root / 'remote-build'
            context = remote_root / tag / 'auth'
            context.mkdir(parents=True)
            (context / 'deleted.ts').write_text('obsolete')
            # Exercise the actual role's context preparation using localhost.
            # Exclude package installation, Docker and all live cluster commands.
            tasks = yaml.safe_load((ROOT / 'ansible/roles/container_images/tasks/build.yml').read_text())
            start = next(i for i, task in enumerate(tasks) if task['name'].startswith('Remove only'))
            stop = next(i for i, task in enumerate(tasks) if task['name'].startswith('Build versioned'))
            selected = json.loads(json.dumps(tasks[start:stop]).replace('/root/openhvx-build', str(remote_root)))
            play = [{'hosts': 'localhost', 'gather_facts': False,
                     'vars': {'image_tag': tag, 'image_release_dir': str(release), 'image_names': ['auth']},
                     'tasks': selected}]
            playbook = root / 'play.yml'
            playbook.write_text(yaml.safe_dump(play))
            subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
                           check=True, capture_output=True, env={**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg')})
            self.assertFalse((context / 'deleted.ts').exists())
            self.assertEqual((context / 'current.ts').read_text(), 'current source')


class MaintenanceSafetyTest(unittest.TestCase):
    def run_platform(self, failure=None):
        calls = []
        def playbook(name, *args, **kwargs):
            calls.append((name, args))
            if name == failure:
                raise RuntimeError('simulated failure')
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / 'linux.yml').touch()
            with patch.object(platform, 'WORK', work), \
                 patch.object(platform, 'ensure_lab_lock'), \
                 patch.object(platform, 'configure_infrastructure') as configure, \
                 patch.object(platform, 'deploy_applications', side_effect=RuntimeError('rollout failed') if failure == 'rollout' else None), \
                 patch.object(platform, 'prepare'), \
                 patch.object(platform, 'run_playbook', side_effect=playbook), \
                 patch.object(sys, 'argv', ['platform-up.py']), \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                if failure:
                    with self.assertRaises(RuntimeError):
                        platform.main()
                else:
                    platform.main()
                if failure == 'maintenance':
                    configure.assert_not_called()
        return calls

    def test_failed_preflight_never_mutates_infrastructure(self):
        self.assertEqual(self.run_platform('maintenance'), [('maintenance', ('-e', 'maintenance_action=enter'))])

    def test_failed_rollout_leaves_gate_closed(self):
        calls = self.run_platform('rollout')
        self.assertNotIn(('maintenance', ('-e', 'maintenance_action=exit')), calls)

    def test_successful_rollout_reopens_admission(self):
        self.assertEqual(self.run_platform()[-1], ('maintenance', ('-e', 'maintenance_action=exit')))


class WorkstationLockTest(unittest.TestCase):
    def test_nested_commands_share_the_lock_and_a_competitor_is_refused(self):
        import fcntl
        script = ROOT / 'scripts/with-lab-lock.sh'
        # Copy the launcher so this test never contends with a real lab operation.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scripts').mkdir()
            local = root / 'scripts/with-lab-lock.sh'
            shutil.copy2(script, local)
            env = {k: v for k, v in os.environ.items() if k != 'OPENHVX_LAB_LOCK_ROOT'}
            result = subprocess.run([str(local), str(local), 'true'], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0)
            with (root / '.lab/deployment.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run([str(local), 'true'], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'Another lab operation', result.stderr)


class CephReconciliationTest(unittest.TestCase):
    def decision(self, name, variables):
        from ansible.parsing.dataloader import DataLoader
        from ansible.template import Templar
        from ansible.playbook.conditional import Conditional
        tasks = yaml.safe_load((ROOT / 'ansible/roles/ceph/tasks/cluster.yml').read_text())
        task = next(task for task in tasks if task['name'] == name)
        loader = DataLoader()
        conditional = Conditional(loader=loader)
        conditional.when = [task['when']]
        return conditional.evaluate_conditional(Templar(loader=loader, variables=variables), variables)

    def test_monitor_count_checks_live_state_including_missing_service(self):
        name = 'Place three monitors when the declared count differs'
        for count, expected in [(3, False), (1, True), (None, True)]:
            spec = [] if count is None else [{'placement': {'count': count}}]
            with self.subTest(count=count):
                self.assertEqual(self.decision(name, {'monitor_specification': {'stdout': json.dumps(spec)}}), expected)

    def test_iscsi_ignores_ceph_defaults_but_detects_changes_to_owned_fields(self):
        name = 'Apply the iSCSI service only when managed settings differ'
        desired = {'pool': 'rbd', 'api_secure': False}
        variables = {
            'groups': {'ceph': ['c1', 'c2', 'c3']}, 'desired_iscsi': desired,
            'live_iscsi': {'placement': {'hosts': ['c3', 'c2', 'c1']},
                           'spec': {**desired, 'ceph_added_default': True}},
        }
        self.assertFalse(self.decision(name, variables))
        variables['live_iscsi']['spec']['pool'] = 'wrong-pool'
        self.assertTrue(self.decision(name, variables))
        variables['live_iscsi'] = {}
        self.assertTrue(self.decision(name, variables))


class CredentialRecoveryTest(unittest.TestCase):
    def test_missing_credentials_on_existing_installation_are_not_regenerated(self):
        credentials = load('credential_safety', 'prepare-platform-secrets.py')
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / 'linux.yml').touch()
            with patch.object(credentials, 'WORK', work), self.assertRaisesRegex(ValueError, 'restore'):
                credentials.prepare_credentials()
            self.assertFalse((work / 'secrets.yml').exists())

    def test_failed_signing_keeps_previous_certificate_and_specification(self):
        credentials = load('certificate_safety', 'prepare-platform-secrets.py')
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for suffix, value in [('crt', 'existing certificate'), ('key', 'existing key'), ('ext', 'old specification')]:
                (work / ('ingress.' + suffix)).write_text(value)
            failure = subprocess.CalledProcessError(1, ['openssl'])
            with patch.object(credentials, 'WORK', work), \
                 patch.object(credentials.subprocess, 'run', side_effect=[None, failure]), \
                 self.assertRaises(subprocess.CalledProcessError):
                credentials.prepare_certificate('ingress', 'example.test', ['DNS:example.test'])
            self.assertEqual((work / 'ingress.crt').read_text(), 'existing certificate')
            self.assertEqual((work / 'ingress.ext').read_text(), 'old specification')
