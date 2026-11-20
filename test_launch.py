"""Windows launcher regressions, including the ShellExecute double-click path."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
POWERSHELL = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
USER32 = ctypes.windll.user32
CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
USER32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
USER32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
USER32.IsWindow.argtypes = [wintypes.HWND]


def app_windows():
    found = set()
    @CALLBACK
    def collect(hwnd, _):
        title = ctypes.create_unicode_buffer(256)
        USER32.GetWindowTextW(hwnd, title, len(title))
        if title.value == '图片蒙版工具':
            found.add(hwnd)
        return True
    USER32.EnumWindows(collect, 0)
    return found


class LauncherTests(unittest.TestCase):
    def test_broken_py_does_not_block_explicit_or_discovered_python(self):
        with tempfile.TemporaryDirectory(prefix='mask launcher ') as tmp:
            folder = Path(tmp)
            shutil.copy2(ROOT / 'launch.ps1', folder)
            (folder / 'launcher.py').write_text(
                'from pathlib import Path\nPath(__file__).with_name("ok").write_text("ok")\n', encoding='utf-8')
            (folder / 'py.cmd').write_bytes(b'@echo off\r\necho broken launcher 1>&2\r\nexit /b 1\r\n')
            env = os.environ.copy()
            env['PATH'] = str(folder) + ';' + str(Path(sys.executable).parent) + ';' + str(Path(os.environ['SystemRoot']) / 'System32')
            for explicit in (True, False):
                with self.subTest(explicit=explicit):
                    env.pop('IMAGE_MASK_PYTHON', None)
                    if explicit:
                        env['IMAGE_MASK_PYTHON'] = sys.executable
                    result = subprocess.run([POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                             '-File', str(folder / 'launch.ps1')], env=env,
                                            capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue((folder / 'ok').exists())
                    (folder / 'ok').unlink()

    def launch_and_close(self, start):
        before = app_windows()
        start()
        opened = set()
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                opened = app_windows() - before
                if opened:
                    break
                time.sleep(.1)
            self.assertTrue(opened, 'No application window appeared')
        finally:
            for hwnd in opened:
                USER32.PostMessageW(hwnd, 0x0010, 0, 0)
            deadline = time.monotonic() + 10
            while any(USER32.IsWindow(hwnd) for hwnd in opened) and time.monotonic() < deadline:
                time.sleep(.1)
        self.assertFalse(any(USER32.IsWindow(hwnd) for hwnd in opened))

    def test_cmd_in_gbk_and_utf8_consoles(self):
        for codepage in (936, 65001):
            with self.subTest(codepage=codepage):
                def start():
                    result = subprocess.run(
                        'cmd.exe /d /c "chcp {} >nul & call 启动.cmd"'.format(codepage),
                        cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.launch_and_close(start)

    def test_double_click_shell_association(self):
        self.launch_and_close(lambda: os.startfile(str(ROOT / '启动.cmd')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
