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
        from PySide6.QtWidgets import QApplication, QLabel
        from concurrent.futures import ThreadPoolExecutor
        from controller import Hub
        from desktop import Notice, RootAdapter
        app = QApplication.instance() or QApplication([])
        label = QLabel()
        download, helper = threading.Event(), threading.Event()
        closed = []
        main_thread = threading.get_ident()
        class Button:
            def configure(self, **kwargs):
                pass
        class Root:
            def after(self, delay, callback):
                RootAdapter.after(SimpleNamespace(window=label), delay, callback)
            def destroy(self):
                closed.append(True)
        pool = ThreadPoolExecutor(1)
        hub = SimpleNamespace(update_release={'version': '9.0.0'}, update_busy=False, busy=False,
                              notice=Notice(label), check_button=Button(), update_button=Button(),
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
