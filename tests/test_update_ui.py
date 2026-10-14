import importlib.util
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires Qt')
class UpdateUiTests(unittest.TestCase):
    def test_progress_and_helper_wait_keep_ui_responsive(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication, QLabel, QPushButton
        from concurrent.futures import ThreadPoolExecutor
        from controller import Hub
        from desktop import Notice, RootAdapter
        app = QApplication.instance() or QApplication([])
        label = QLabel()
        download, helper = threading.Event(), threading.Event()
        closed = []
        main_thread = threading.get_ident()
        class Root:
            def after(self, delay, callback):
                RootAdapter.after(SimpleNamespace(window=label), delay, callback)
            def destroy(self):
                closed.append(True)
        pool = ThreadPoolExecutor(1)
        hub = SimpleNamespace(update_release={'version': '9.0.0'}, update_busy=False, busy=False,
                              notice=Notice(label), check_button=QPushButton(), update_button=QPushButton(),
                              root=Root(), pool=pool, persist_sessions=lambda: None)
        hub.background = lambda task, done: Hub.background(hub, task, done)
        def stage(release, directory, progress):
            progress('Downloading v9.0.0: 42%')
            download.wait(4)
            return Path(directory)
        def apply(*args):
            self.assertNotEqual(threading.get_ident(), main_thread)
            helper.wait(4)
        def until(predicate):
            deadline = time.monotonic() + 3
            while not predicate() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
            self.assertTrue(predicate(), label.text())
        try:
            with tempfile.TemporaryDirectory() as directory, patch('controller.DATA', Path(directory)), patch('controller.stage_release', side_effect=stage), patch('controller.apply_and_restart', side_effect=apply):
                Hub.update_now(hub)
                until(lambda: '42%' in label.text())
                download.set()
                until(lambda: 'startup confirmation' in label.text())
                self.assertFalse(closed)
                helper.set()
                until(lambda: bool(closed))
                self.assertIn('restarting', label.text())
        finally:
            download.set()
            helper.set()
            hub.update_busy = False
            pool.shutdown(wait=True)
            app.processEvents()


    def test_actual_desktop_update_buttons_check_download_and_recover_from_error(self):
        import os
        import json
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        import controller
        from desktop import Desktop
        from core import DEFAULT, atomic_text
        import copy
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings, sessions = root / 'settings.json', root / 'sessions.json'
            atomic_text(settings, json.dumps(copy.deepcopy(DEFAULT)))
            with patch.object(controller, 'CONFIG', settings), patch.object(controller, 'SESSIONS', sessions), patch.object(controller, 'DATA', root):
                window = Desktop()
                def until(predicate):
                    deadline = time.monotonic() + 3
                    while not predicate() and time.monotonic() < deadline:
                        app.processEvents()
                        time.sleep(.01)
                    self.assertTrue(predicate(), window.notice.label.text())
                try:
                    self.assertFalse(window.update_button.isEnabled())
                    with patch('controller.check_release', return_value={'version': '9.0.0'}):
                        window.check_button.click()
                        self.assertIn('Checking GitHub', window.notice.label.text())
                        self.assertFalse(window.check_button.isEnabled())
                        until(lambda: not window.update_busy)
                    self.assertTrue(window.check_button.isEnabled())
                    self.assertTrue(window.update_button.isEnabled())
                    self.assertIn('9.0.0', window.notice.label.text())
                    with patch('controller.stage_release', side_effect=OSError('synthetic network failure')) as stage:
                        window.update_button.click()
                        self.assertFalse(window.update_button.isEnabled())
                        until(lambda: not window.update_busy)
                        self.assertEqual(stage.call_count, 1)
                    self.assertIn('synthetic network failure', window.notice.label.text())
                    self.assertTrue(window.check_button.isEnabled())
                    self.assertTrue(window.update_button.isEnabled())
                    with patch('controller.check_release', return_value=None):
                        window.check_button.click()
                        until(lambda: not window.update_busy)
                    self.assertIn('up to date', window.notice.label.text())
                    self.assertFalse(window.update_button.isEnabled())
                finally:
                    window.force_close = True
                    window.close()
                    app.processEvents()
