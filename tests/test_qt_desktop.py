import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HAS_QT = importlib.util.find_spec('PySide6') is not None


@unittest.skipUnless(HAS_QT, 'Qt desktop checks require PySide6')
class QtDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_encounter_style_controls_and_saved_rendering(self):
        import controller
        from desktop import Desktop, COLUMNS
        from qt_style import STYLE
        import copy
        from core import DEFAULT, atomic_text, read_status, write_ini
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = copy.deepcopy(DEFAULT)
            config['accounts'] = [dict(id='one', character='Alpha Farm Char', team='Team 1', leader=True)]
            settings, sessions = root / 'settings.json', root / 'sessions.json'
            atomic_text(settings, json.dumps(config))
            with patch.object(controller, 'CONFIG', settings), patch.object(controller, 'SESSIONS', sessions), patch.object(controller, 'DATA', root):
                window = Desktop()
                try:
                    self.assertEqual(window.grid.rowCount(), 1)
                    for key in ('plat', 'storage_plat', 'skeletons', 'funding', 'currency'):
                        self.assertIn(key, COLUMNS)
                    self.assertIn('#14171c', STYLE)
                    self.assertIn('#52d4ba', STYLE)
                    self.assertEqual(window.check_button.text(), 'Check for Updates')
                    self.assertEqual(window.update_button.text(), 'Update Now')
                    self.assertTrue(window.config['teams']['Team 1']['test_mode'])
                    self.assertFalse(window.config['teams']['Team 1']['assemble_only'])
                    window.widgets['one']['render'].setChecked(True)
                    self.assertTrue(json.loads(settings.read_text())['accounts'][0]['rendering'])
                    window.select_all(True)
                    self.assertEqual(window.table.selection(), ('one',))
                    self.assertIsNotNone(window.grid.cellWidget(0, COLUMNS.index('pause')))
                    self.assertIsNotNone(window.grid.cellWidget(0, COLUMNS.index('launch')))
                    from worker import read_ini
                    from PySide6.QtWidgets import QPushButton
                    session = root / 'test-session'
                    session.mkdir()
                    command = session / 'one.command.ini'
                    write_ini(command, {'Control': {'Mode': 'pause', 'DisableRendering': 1}})
                    window.sessions = {'Team 1': {'dir': str(session), 'pids': {'one': 123}}}
                    with patch.object(controller, 'alive', return_value=True):
                        window.grid.cellWidget(0, COLUMNS.index('currency')).click()
                        first = read_ini(command)['Control']['CurrencyRequest']
                        self.assertEqual(read_ini(command)['Control']['Mode'], 'pause')
                        selected_button = next(b for b in window.findChildren(QPushButton) if b.text() == 'Handle Currency Selected')
                        selected_button.click()
                        self.assertNotEqual(read_ini(command)['Control']['CurrencyRequest'], first)
                        self.assertEqual(read_ini(command)['Control']['DisableRendering'], '1')
                    window.show()
                    self.app.processEvents()
                    # CI screenshot is synthetic account data only.
                    shot = os.environ.get('SKELEHUB_PREVIEW')
                    if shot:
                        window.grab().save(shot)
                finally:
                    window.force_close = True
                    window.close()
                    self.app.processEvents()
