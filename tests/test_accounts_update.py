import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from accounts import read_characters, merge_accounts, validate_install
from core import DEFAULT, snapshot
from updater import validate_package, version_tuple, check_release
from version import worker_name


class AccountsTests(unittest.TestCase):
    def test_import_and_session_never_copy_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            ini = Path(directory) / 'characters.ini'
            ini.write_text('[Example Character]\nEmail=secret@example.invalid\nPwd={SEC}DO_NOT_COPY\nFilePath=C:\\GW1\\Gw.exe\n', encoding='utf-8')
            records = read_characters(ini)
            self.assertEqual(records[0]['dat_path'], r'C:\GW1\Gw.dat')
            config = copy.deepcopy(DEFAULT)
            merge_accounts(config, records)
            self.assertTrue(config['accounts'][0]['leader'])
            session = Path(directory) / 'session'
            snapshot(config, 'Team 1', session)
            text = json.dumps(config) + (session / 'team.ini').read_text(encoding='utf-16')
            self.assertNotIn('secret@example.invalid', text)
            self.assertNotIn('DO_NOT_COPY', text)
            self.assertIn('CharactersINI=', text)
            self.assertIn('LaunchDirect=1', text)

    def test_unicode_ini_and_existing_roles_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            ini = Path(directory) / 'chars.ini'
            ini.write_text('[Example Character]\nEmail=x\nPwd=x\nFilePath=C:\\GW\\Gw.exe\n', encoding='utf-16')
            config = copy.deepcopy(DEFAULT)
            merge_accounts(config, read_characters(ini))
            config['accounts'][0]['team'] = 'Custom'
            config['accounts'][0]['leader'] = False
            merge_accounts(config, read_characters(ini))
            self.assertEqual(len(config['accounts']), 1)
            self.assertEqual(config['accounts'][0]['team'], 'Custom')
            self.assertFalse(config['accounts'][0]['leader'])

    def test_dat_must_match_installation(self):
        validate_install(r'C:\GW\Gw.exe', r'c:\gw\GW.DAT', exists=lambda _: True)
        with self.assertRaises(ValueError):
            validate_install(r'C:\GW\Gw.exe', r'C:\Other\Gw.dat', exists=lambda _: True)
        with self.assertRaises(ValueError):
            validate_install(r'C:\GW\Gw.exe', r'C:\GW\Gw.dat', exists=lambda _: False)

    def test_snapshot_exports_selected_roster(self):
        c = copy.deepcopy(DEFAULT)
        c['accounts'] = [dict(id='one', character='First Character', team='Team 1', leader=True)]
        with tempfile.TemporaryDirectory() as directory:
            members = snapshot(c, 'Team 1', Path(directory))
            self.assertEqual(len(members), 1)
            self.assertNotIn('Member2', (Path(directory) / 'team.ini').read_text(encoding='utf-16'))


class UpdateTests(unittest.TestCase):
    def package(self, entries):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'update.zip'
        with zipfile.ZipFile(path, 'w') as z:
            for name, data in entries.items():
                z.writestr(name, data)
        return path

    def test_version_comparison(self):
        self.assertGreater(version_tuple('v0.10.0'), version_tuple('0.2.0'))
        for v in ('../0.2.0', 'latest', '0.2.0-beta'):
            with self.assertRaises(ValueError):
                version_tuple(v)

    def test_valid_package_uses_new_worker_filename(self):
        path = self.package({'Skelefarm Hub.exe': b'MZfake-hub', worker_name('0.3.0'): b'MZfake-worker', 'README.md': b'docs'})
        self.assertEqual(len(validate_package(path, '0.3.0')), 3)
        self.assertNotEqual(worker_name('0.2.0'), worker_name('0.3.0'))

    def test_rejects_traversal_credentials_and_wrong_worker(self):
        base = {'Skelefarm Hub.exe': b'MZhub', worker_name('0.3.0'): b'MZworker'}
        for extra in ('../settings.json', 'characters.ini', 'Skelefarm.exe', r'..\x.exe'):
            with self.assertRaises(ValueError):
                validate_package(self.package(dict(base, **{extra: b'x'})), '0.3.0')

    def test_missing_or_invalid_executable_rejected(self):
        for entries in ({'Skelefarm Hub.exe': b'MZ'}, {'Skelefarm Hub.exe': b'bad', worker_name('0.3.0'): b'MZ'}):
            with self.assertRaises(ValueError):
                validate_package(self.package(entries), '0.3.0')

    def test_release_uses_expected_asset_and_repository(self):
        release = {'tag_name': 'v0.3.0', 'assets': [{'name': 'SkeleHub-0.3.0-windows.zip',
                   'browser_download_url': 'https://github.com/dasaright/SkeleHub/releases/download/v0.3.0/SkeleHub-0.3.0-windows.zip', 'size': 22}]}
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(release).encode())):
            self.assertEqual(check_release('0.2.0')['version'], '0.3.0')
        release['assets'][0]['browser_download_url'] = 'https://other.invalid/file.zip'
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(release).encode())):
            with self.assertRaises(ValueError):
                check_release('0.2.0')


if __name__ == '__main__':
    unittest.main()


class DownloadAndHandoffTests(unittest.TestCase):
    def archive(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as z:
            z.writestr('Skelefarm Hub.exe', b'MZhub')
            z.writestr(worker_name('0.3.0'), b'MZworker')
        return output.getvalue()

    def test_stage_download_and_hash(self):
        import hashlib
        from updater import stage_release
        data = self.archive()
        release = dict(version='0.3.0', url='https://example.invalid/download', size=len(data),
                       digest='sha256:' + hashlib.sha256(data).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / 'settings.json'
            sentinel.write_text('preserve me')
            with patch('urllib.request.urlopen', return_value=io.BytesIO(data)):
                stage = stage_release(release, directory)
            self.assertTrue((stage / 'apply.ps1').is_file())
            self.assertEqual((stage / worker_name('0.3.0')).read_bytes(), b'MZworker')
            self.assertEqual(sentinel.read_text(), 'preserve me')

    def test_bad_checksum_and_incomplete_download_clean_stage(self):
        from updater import stage_release
        data = self.archive()
        for size, digest in ((len(data), 'sha256:wrong'), (len(data) + 1, None)):
            with tempfile.TemporaryDirectory() as directory:
                with patch('urllib.request.urlopen', return_value=io.BytesIO(data)):
                    with self.assertRaises(ValueError):
                        stage_release(dict(version='0.3.0', url='https://example.invalid/download', size=size, digest=digest), directory)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_helper_failure_keeps_hub_open(self):
        from updater import apply_and_restart
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            with patch('updater.os.name', 'nt'), patch('updater.subprocess.Popen') as popen:
                popen.return_value.poll.return_value = 1
                with self.assertRaises(RuntimeError):
                    apply_and_restart(stage, stage, 1234)
            self.assertTrue((stage / 'cancelled').exists())

    def test_helper_readiness_and_arguments(self):
        from updater import apply_and_restart
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            (stage / 'ready').touch()
            with patch('updater.os.name', 'nt'), patch('updater.subprocess.Popen') as popen:
                apply_and_restart(stage, stage, 1234)
                args = popen.call_args.args[0]
            self.assertIn('-HubPid', args)
            self.assertIn('1234', args)
            self.assertNotIn('Stop-Process', ' '.join(args))
