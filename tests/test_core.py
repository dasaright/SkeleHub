import configparser
import copy
import os
from pathlib import Path
import tempfile
import time
import unittest
from core import DEFAULT, snapshot, validate, write_ini, read_status, save_config


def team_config():
    c = copy.deepcopy(DEFAULT)
    c['accounts'] = [
        dict(id='a1', character='Alpha Farm Char', team='Team 1', leader=True),
        dict(id='a2', character='Beta Farm Char', team='Team 1', leader=False),
        dict(id='a3', character='Gamma Farm Char', team='Team 1', leader=False),
    ]
    return c


class ConfigTests(unittest.TestCase):
    def test_valid_team(self):
        validate(team_config())

    def test_missing_or_duplicate_leader(self):
        for count in (0, 2):
            c = team_config()
            for i, a in enumerate(c['accounts']):
                a['leader'] = i < count
            with self.assertRaises(ValueError):
                validate(c)

    def test_duplicate_char_case_insensitive(self):
        c = team_config()
        c['accounts'][1]['character'] = c['accounts'][0]['character'].lower()
        with self.assertRaises(ValueError):
            validate(c)

    def test_no_path_injection_id(self):
        c = team_config()
        c['accounts'][0]['id'] = '../other'
        with self.assertRaises(ValueError):
            validate(c)

    def test_game_party_capacity(self):
        c = team_config()
        for i in range(6):
            c['accounts'].append(dict(id=f'b{i}', character=f'Example Char {i}', team='Team 1', leader=False))
        with self.assertRaises(ValueError):
            validate(c)

    def test_no_random_district(self):
        c = team_config()
        c['teams']['Team 1']['district'] = 0
        with self.assertRaises(ValueError):
            validate(c)

    def test_snapshot_includes_only_team_and_is_frozen(self):
        c = team_config()
        c['teams']['Other'] = copy.deepcopy(c['teams']['Team 1'])
        c['accounts'].append(dict(id='other', character='Other Character', team='Other', leader=True))
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            snapshot(c, 'Team 1', directory)
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(directory / 'team.ini', encoding='utf-16')
            self.assertEqual(parser['Team']['Count'], '3')
            self.assertEqual(parser['Team']['Leader'], 'a1')
            self.assertEqual(parser['Team']['AssembleOnly'], '0')
            c['accounts'][0]['character'] = 'Changed'
            self.assertEqual(parser['Member1']['Character'], 'Alpha Farm Char')
            self.assertFalse((directory / 'other.command.ini').exists())
            command = configparser.ConfigParser()
            command.read(directory / 'a2.command.ini', encoding='utf-16')
            self.assertEqual(command['Control']['Mode'], 'run')

    def test_status_round_trip_unicode_and_percent(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'status.ini'
            write_ini(p, {'Worker': {'State': 'Capture 100% — verified', 'Runs': 3}})
            self.assertEqual(read_status(p)['state'], 'Capture 100% — verified')
            self.assertEqual(read_status(p)['runs'], '3')
            self.assertFalse(list(p.parent.glob('*.tmp')))

    def test_stale_or_partial_status_not_ready(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'status.ini'
            write_ini(p, {'Worker': {'State': 'Ready'}})
            os.utime(p, (time.time() - 20, time.time() - 20))
            self.assertEqual(read_status(p), {})
            p.write_bytes(b'partial-write')
            self.assertEqual(read_status(p), {})

    def test_invalid_config_does_not_overwrite_saved_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'settings.json'
            c = team_config()
            save_config(p, c)
            before = p.read_bytes()
            c['accounts'][0]['leader'] = False
            with self.assertRaises(ValueError):
                save_config(p, c)
            self.assertEqual(before, p.read_bytes())


if __name__ == '__main__':
    unittest.main()


class AtomicSharingTests(unittest.TestCase):
    def test_status_replace_retries_windows_sharing_lock(self):
        from unittest.mock import patch
        from core import atomic_text
        import os
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'status.ini'
            replace = os.replace
            attempts = []
            def sharing_then_replace(source, dest):
                attempts.append(True)
                if len(attempts) < 3:
                    raise PermissionError('sharing violation')
                return replace(source, dest)
            with patch('core.os.replace', side_effect=sharing_then_replace), patch('core.time.sleep'):
                atomic_text(target, 'complete status')
            self.assertEqual(target.read_text(), 'complete status')
            self.assertEqual(len(attempts), 3)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])
