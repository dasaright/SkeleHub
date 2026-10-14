import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from core import write_control, write_ini
from controller import Hub


class RecoveryTests(unittest.TestCase):
    def setup_hub(self, directory):
        path = Path(directory)
        account = dict(id='one', character='Alpha', team='Team 1', gw_exe='C:/Games/Gw.exe')
        hub = SimpleNamespace(config={'accounts': [account]}, sessions={'Team 1': {'dir': str(path), 'pids': {'one': 123}}},
                              busy=False, update_busy=False, launch_queue=[], notice=SimpleNamespace(set=lambda text: None))
        hub.launch_next = lambda: hub.launch_queue.pop(0)
        write_control(path / 'one.command.ini', mode='run')
        write_ini(path / 'one.status.ini', {'Worker': {'PID': 123, 'Phase': 'Error', 'GamePID': 456}})
        return hub

    def test_failed_account_stops_then_relaunches_after_worker_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = self.setup_hub(directory)
            with patch('controller.dismiss_crash_dialogs', return_value=[]), patch('controller.alive', return_value=True), patch('controller.time.monotonic', return_value=100) as clock:
                Hub.recovery_tick(hub)
                clock.return_value = 109
                Hub.recovery_tick(hub)
            state = hub._recovery[(directory, 'one')]
            self.assertTrue(state['pending'])
            self.assertEqual(state['attempts'], 1)
            self.assertFalse(hub.busy)
            with patch('controller.dismiss_crash_dialogs', return_value=[]), patch('controller.alive', return_value=False), patch('controller.time.monotonic', return_value=113):
                Hub.recovery_tick(hub)
            self.assertTrue(hub.busy)
            self.assertFalse(state['pending'])

    def test_dead_client_detected_without_worker_error_and_pause_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = self.setup_hub(directory)
            path = Path(directory)
            write_control(path / 'one.command.ini', mode='pause')
            write_ini(path / 'one.status.ini', {'Worker': {'PID': 123, 'Phase': 'Paused', 'GamePID': 456}})
            with patch('controller.dismiss_crash_dialogs', return_value=[]), patch('controller.alive', side_effect=lambda pid: pid == 123), patch('controller.time.monotonic', return_value=100) as clock:
                Hub.recovery_tick(hub)
                clock.return_value = 109
                Hub.recovery_tick(hub)
            self.assertTrue(hub._recovery[(directory, 'one')]['pending'])
            with patch('controller.dismiss_crash_dialogs', return_value=[]), patch('controller.alive', return_value=False), patch('controller.time.monotonic', return_value=113):
                Hub.recovery_tick(hub)
            import configparser
            control = configparser.ConfigParser()
            control.read(path / 'one.command.ini', encoding='utf-16')
            self.assertEqual(control['Control']['Mode'], 'pause')
            self.assertTrue(hub.busy)

    def test_stalled_loading_restarts_immediately_without_extra_error_delay(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = self.setup_hub(directory)
            write_ini(Path(directory) / 'one.status.ini', {'Worker': {'PID': 123, 'Phase': 'Error', 'GamePID': 456, 'RestartRequired': 1}})
            with patch('controller.dismiss_crash_dialogs', return_value=[]), patch('controller.alive', return_value=True), patch('controller.terminate_stalled_account') as terminate, patch('controller.time.monotonic', return_value=100):
                Hub.recovery_tick(hub)
            terminate.assert_called_once_with(123, 456)
            self.assertTrue(hub._recovery[(directory, 'one')]['pending'])

    def test_stale_bridge_heartbeat_restarts_owned_account_even_if_worker_alive(self):
        import os
        import time
        with tempfile.TemporaryDirectory() as directory:
            hub = self.setup_hub(directory)
            path = Path(directory) / 'one.status.ini'
            write_ini(path, {'Worker': {'PID': 123, 'Phase': 'Fight', 'GamePID': 456}})
            os.utime(path, (time.time() - 11, time.time() - 11))
            with patch('controller.dismiss_crash_dialogs', return_value=[]), patch('controller.alive', return_value=True), patch('controller.terminate_stalled_account') as terminate, patch('controller.time.monotonic', return_value=100):
                Hub.recovery_tick(hub)
            terminate.assert_called_once_with(123, 456)

    def test_manual_stop_cancels_pending_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = self.setup_hub(directory)
            with patch('controller.dismiss_crash_dialogs', return_value=[{'pid': 456, 'path': 'C:/Games/Gw.exe'}]), patch('controller.alive', return_value=True), patch('controller.time.monotonic', return_value=100):
                Hub.recovery_tick(hub)
            write_control(Path(directory) / 'one.command.ini', mode='stop', close_game=True)
            with patch('controller.dismiss_crash_dialogs', return_value=[]), patch('controller.alive', return_value=False), patch('controller.time.monotonic', return_value=104):
                Hub.recovery_tick(hub)
            self.assertFalse(hub._recovery[(directory, 'one')]['pending'])
            self.assertFalse(hub.launch_queue)

    def test_retry_limit_does_not_loop_forever(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = self.setup_hub(directory)
            hub._recovery = {(directory, 'one'): dict(attempts=3, pending=False, since=80)}
            with patch('controller.dismiss_crash_dialogs', return_value=[]), patch('controller.alive', return_value=False), patch('controller.time.monotonic', return_value=100):
                Hub.recovery_tick(hub)
            self.assertFalse(hub.launch_queue)
            self.assertFalse(hub._recovery[(directory, 'one')]['pending'])


@unittest.skipUnless(__import__('os').name == 'nt', 'Native crash dialogs require Windows')
class WindowsCrashDialogTests(unittest.TestCase):
    def test_dont_send_is_clicked_only_for_owned_process(self):
        import ctypes
        import os
        from ctypes import wintypes
        from windows_recovery import dismiss_crash_dialogs
        user = ctypes.WinDLL('user32', use_last_error=True)
        user.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
        user.CreateWindowExW.restype = wintypes.HWND
        user.DestroyWindow.argtypes = [wintypes.HWND]
        window = user.CreateWindowExW(0, 'STATIC', 'Synthetic Guild Wars crash', 0x10CF0000,
                                      0, 0, 320, 120, None, None, None, None)
        self.assertTrue(window)
        try:
            button = user.CreateWindowExW(0, 'BUTTON', "Do&n't Send", 0x50000000,
                                          10, 10, 160, 30, window, 101, None, None)
            self.assertTrue(button)
            self.assertEqual(dismiss_crash_dialogs(set(), []), [])
            found = dismiss_crash_dialogs({os.getpid()}, [])
            self.assertTrue(any(result['pid'] == os.getpid() for result in found))
        finally:
            user.DestroyWindow(window)
