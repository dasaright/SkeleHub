"""Dismiss crash-report dialogs only for the hub's launched Guild Wars clients."""
import os
from pathlib import Path


def dismiss_crash_dialogs(owned_pids, game_paths):
    if os.name != 'nt':
        return []
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumChildWindows.argtypes = [wintypes.HWND, callback_type, wintypes.LPARAM]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    paths = {os.path.normcase(os.path.abspath(p)) for p in game_paths if p}
    found = []
    def text(hwnd):
        value = ctypes.create_unicode_buffer(4096)
        user.GetWindowTextW(hwnd, value, len(value))
        return value.value
    def executable(pid):
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ''
        try:
            value = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(value))
            return os.path.normcase(value.value) if kernel.QueryFullProcessImageNameW(handle, 0, value, ctypes.byref(size)) else ''
        finally:
            kernel.CloseHandle(handle)
    @callback_type
    def window(hwnd, unused):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        path = executable(pid.value)
        owned = pid.value in owned_pids or path in paths
        # Windows Error Reporting can own the dialog instead of Gw.exe.
        wer = Path(path).name.lower() in ('werfault.exe', 'wermgr.exe')
        if not owned and not wer:
            return True
        controls = []
        @callback_type
        def child(control, unused):
            name = ctypes.create_unicode_buffer(80)
            user.GetClassNameW(control, name, len(name))
            controls.append((control, name.value, text(control)))
            return True
        user.EnumChildWindows(hwnd, child, 0)
        content = (text(hwnd) + ' ' + ' '.join(c[2] for c in controls)).lower()
        if not owned and not any(p.lower() in content for p in paths):
            return True
        for control, kind, caption in controls:
            normalized = caption.lower().replace('&', '').replace('’', "'").strip()
            if kind.lower() == 'button' and normalized in ("don't send", 'do not send', "don't send error report"):
                result = ctypes.c_size_t()
                if user.SendMessageTimeoutW(control, 0xF5, 0, 0, 2, 200, ctypes.byref(result)):
                    found.append({'pid': pid.value, 'path': path, 'text': 'Crash report dismissed: Don\'t Send'})
                break
        return True
    user.EnumWindows(window, 0)
    return found
