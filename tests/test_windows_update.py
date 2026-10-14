"""Exercise the real PowerShell helper using harmless temporary test executables."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from updater import HELPER
from version import worker_name


@unittest.skipUnless(os.name == 'nt', 'Real replacement/restart checks require Windows')
class WindowsReplacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.scratch.cleanup)
        root = Path(cls.scratch.name)
        compiler = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
        if not compiler.is_file():
            raise unittest.SkipTest('C# compiler unavailable for temporary helper test executables')
        source = root / 'Process.cs'
        source.write_text('''using System; using System.IO; using System.Threading; using System.Diagnostics;
class TestProcess {
 static void Main(string[] args) {
  if(args.Length > 0 && args[0] == "old") { Thread.Sleep(2500); return; }
  if(args.Length == 0) { File.WriteAllText("restarted.pid", Process.GetCurrentProcess().Id.ToString()); File.WriteAllText("restart-env.txt", Environment.GetEnvironmentVariable("PYINSTALLER_RESET_ENVIRONMENT") + "|" + Environment.GetEnvironmentVariable("_PYI_PARENT_PROCESS_LEVEL")); }
  Thread.Sleep(120000);
 }
}''')
        cls.program = root / 'TestProcess.exe'
        subprocess.run([str(compiler), '/nologo', '/target:exe', '/out:' + str(cls.program), str(source)], check=True, capture_output=True)

    def run_replacement(self, missing_worker):
        with tempfile.TemporaryDirectory(prefix='SkeleHub update test ') as directory:
            data = Path(directory)
            install, stage = data / 'Install folder', data / 'staged'
            install.mkdir()
            stage.mkdir()
            hub = install / 'Skelefarm Hub.exe'
            old_worker = install / worker_name('0.2.0')
            shutil.copy2(self.program, hub)
            shutil.copy2(self.program, old_worker)
            original = hub.read_bytes()
            retired = install / worker_name('0.1.0')
            shutil.copy2(self.program, retired)
            (install / 'my-notes.txt').write_text('keep')
            (install / 'settings.json').write_text('local-settings')
            (install / 'sessions.json').write_text('local-sessions')
            shutil.copy2(self.program, stage / 'Skelefarm Hub.exe')
            # Valid executable overlay makes replacement distinguishable from the old file.
            with (stage / 'Skelefarm Hub.exe').open('ab') as out:
                out.write(b'new-build-marker')
            new_worker = worker_name('0.3.0')
            if not missing_worker:
                shutil.copy2(self.program, stage / new_worker)
            (stage / 'manifest.json').write_text(json.dumps(['Skelefarm Hub.exe', new_worker]))
            (stage / 'apply.ps1').write_text(HELPER, encoding='utf-8-sig')
            old = subprocess.Popen([str(hub), 'old'], cwd=install)
            worker = subprocess.Popen([str(old_worker), 'worker'], cwd=install)
            restarted_pid = None
            try:
                helper = subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                    str(stage / 'apply.ps1'), '-HubPid', str(old.pid), '-InstallDir', str(install), '-StagingDir', str(stage)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, '_PYI_PARENT_PROCESS_LEVEL': '1', '_PYI_ARCHIVE_FILE': str(hub), '_PYI_PARENT_PROCESS_ID': '99999999'})
                stdout, stderr = helper.communicate(timeout=90)
                self.assertEqual(helper.returncode, 0, stderr.decode(errors='replace'))
                report = json.loads((data / 'last-update.json').read_text(encoding='utf-8-sig'))
                self.assertEqual(report['success'], not missing_worker)
                self.assertIsNone(worker.poll(), 'Updater stopped the active worker')
                self.assertEqual(old_worker.read_bytes(), original)
                self.assertEqual((install / 'settings.json').read_text(), 'local-settings')
                self.assertEqual((install / 'sessions.json').read_text(), 'local-sessions')
                if missing_worker:
                    self.assertEqual(hub.read_bytes(), original, 'Rollback failed to restore the hub')
                else:
                    self.assertTrue(hub.read_bytes().endswith(b'new-build-marker'))
                    self.assertTrue((install / new_worker).exists())
                    self.assertFalse(retired.exists())
                    self.assertEqual((install / 'my-notes.txt').read_text(), 'keep')
                deadline = time.monotonic() + 10
                while not (install / 'restarted.pid').exists() and time.monotonic() < deadline:
                    time.sleep(0.1)
                restarted_pid = int((install / 'restarted.pid').read_text())
                self.assertGreater(restarted_pid, 0)
                self.assertEqual((install / 'restart-env.txt').read_text(), '1|')
            finally:
                # Clean up only the temporary processes this test created.
                for process in (old, worker):
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=10)
                if restarted_pid:
                    subprocess.run(['taskkill', '/PID', str(restarted_pid), '/F'], capture_output=True, check=False)
                    time.sleep(0.3)

    def test_replaces_hub_restarts_and_preserves_active_worker(self):
        self.run_replacement(missing_worker=False)

    def test_failed_update_rolls_back_and_restarts_old_hub(self):
        self.run_replacement(missing_worker=True)
