import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from core import DEFAULT, atomic_text
from accounts import save_character
from controller import Hub
from portable import prepare_data


class PortableBulkTests(unittest.TestCase):
    def test_migrates_credentials_and_sessions_without_overwriting_portable_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy, install = root / 'old', root / 'bot'
            legacy.mkdir()
            session = legacy / 'sessions/one'
            session.mkdir(parents=True)
            (session / 'one.log').write_text('old log')
            chars = root / 'original.ini'
            chars.write_text('[Alpha]\nEmail=x\nPwd=protected\nFilePath=C:\\GW\\Gw.exe')
            atomic_text(legacy / 'settings.json', json.dumps(dict(accounts=[dict(characters_ini=str(chars))])))
            atomic_text(legacy / 'sessions.json', json.dumps({'Team 1': {'dir': str(session), 'pids': {}}}))
            data = prepare_data(install, legacy)
            self.assertEqual(data, install / 'Files')
            config = json.loads((data / 'settings.json').read_text())
            target = Path(config['accounts'][0]['characters_ini'])
            self.assertEqual(target.parent, data)
            self.assertEqual(target.read_bytes(), chars.read_bytes())
            self.assertEqual(json.loads((data / 'sessions.json').read_text())['Team 1']['dir'], str(data / 'sessions/one'))
            self.assertEqual((data / 'sessions/one/one.log').read_text(), 'old log')
            atomic_text(data / 'settings.json', '{"new": true}')
            prepare_data(install, legacy)
            self.assertEqual(json.loads((data / 'settings.json').read_text()), {'new': True})

    def test_completed_updates_cleanup_and_legacy_archive(self):
        from portable import cleanup_updates, archive_legacy
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / 'SkelefarmHub'
            legacy.mkdir()
            (legacy / 'settings.json').write_text('{"accounts": []}')
            data = prepare_data(root / 'bot', legacy)
            complete = data / 'update-complete'
            complete.mkdir()
            (complete / 'update.log').write_text('Update applied; hub restarted.')
            (complete / 'package.zip').write_text('retired installer')
            failed = data / 'update-failed'
            failed.mkdir()
            (failed / 'update.log').write_text('failure details')
            cleanup_updates(data)
            self.assertFalse(complete.exists())
            self.assertTrue((data / 'logs/update-complete.log').exists())
            self.assertTrue(failed.exists())
            archive_legacy(data)
            self.assertFalse(legacy.exists())
            self.assertTrue((data / 'migration-backup/settings.json').exists())

    def hub(self, root):
        hub = SimpleNamespace(config=copy.deepcopy(DEFAULT), notice=SimpleNamespace(set=lambda text: None))
        hub.save_draft = lambda: Hub.save_draft(hub)
        return hub

    def records(self, count):
        return [dict(character=f'Character {i}', email=f'user{i}@example.invalid', gw_exe=r'C:\GW\Gw.exe', password='synthetic') for i in range(count)]

    def test_ten_accounts_saved_to_managed_ini_and_split_at_party_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hub = self.hub(root)
            def save(*args, **kwargs):
                return save_character(*args, **kwargs, protector=lambda value: '{DPAPI}synthetic')
            with patch('controller.DATA', root), patch('controller.CONFIG', root / 'settings.json'), patch('controller.validate_install'), patch('controller.save_character', side_effect=save), patch('controller.messagebox.showerror') as error:
                Hub.save_accounts(hub, self.records(10))
            error.assert_not_called()
            self.assertEqual(len(hub.config['accounts']), 10)
            self.assertEqual(sum(a['team'] == 'Team 1' for a in hub.config['accounts']), 8)
            self.assertEqual(sum(a['team'] == 'Team 2' for a in hub.config['accounts']), 2)
            self.assertTrue((root / 'characters.ini').is_file())
            settings = (root / 'settings.json').read_text()
            self.assertNotIn('synthetic', settings)
            self.assertNotIn('@example.invalid', settings)

    def test_invalid_batch_and_credential_failure_restore_previous_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hub = self.hub(root)
            chars = root / 'characters.ini'
            chars.write_text('[Existing]\nEmail=old\nPwd=old\nFilePath=old')
            original = chars.read_bytes()
            records = self.records(2)
            counter = []
            def save(*args, **kwargs):
                counter.append(1)
                if len(counter) == 2:
                    raise OSError('Synthetic write failure')
                save_character(*args, **kwargs, protector=lambda value: '{DPAPI}synthetic')
            with patch('controller.DATA', root), patch('controller.CONFIG', root / 'settings.json'), patch('controller.validate_install'), patch('controller.save_character', side_effect=save), patch('controller.messagebox.showerror') as error:
                Hub.save_accounts(hub, records)
            error.assert_called_once()
            self.assertEqual(hub.config['accounts'], [])
            self.assertEqual(chars.read_bytes(), original)
            self.assertFalse((root / 'settings.json').exists())
