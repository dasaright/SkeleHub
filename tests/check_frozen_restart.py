"""Run the updater from a real onefile build, including stale bootloader environment."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

PROBE = '''import json, os, shutil, sys
from pathlib import Path
from updater import apply_and_restart, HELPER
root = Path(sys.executable).parent
if len(sys.argv) > 1:
    stage = root / 'Files' / 'update-probe'
    stage.mkdir(parents=True)
    shutil.copy2(sys.executable, stage / 'Skelefarm Hub.exe')
    shutil.copy2(sys.executable, stage / 'Skelefarm-worker-99.0.0.exe')
    (stage / 'manifest.json').write_text(json.dumps(['Skelefarm Hub.exe', 'Skelefarm-worker-99.0.0.exe']))
    (stage / 'apply.ps1').write_text(HELPER, encoding='utf-8-sig')
    apply_and_restart(stage, root, os.getpid())
else:
    (root / 'restarted.json').write_text(json.dumps({'pid': os.getpid(), 'home': sys._MEIPASS}))
'''


def main():
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='SkeleHub frozen restart ') as directory:
        root = Path(directory)
        script = root / 'probe.py'
        script.write_text(PROBE)
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed', '--uac-admin',
                        '--paths', str(repo), '--name', 'Skelefarm Hub', '--distpath', str(root / 'install'),
                        '--workpath', str(root / 'build'), '--specpath', str(root), str(script)], check=True, cwd=root)
        install = root / 'install'
        process = subprocess.Popen([str(install / 'Skelefarm Hub.exe'), 'update'], cwd=install)
        try:
            process.wait(timeout=45)
            if process.returncode:
                raise RuntimeError(f'Frozen updater exited with {process.returncode}')
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline and not (install / 'restarted.json').exists():
                time.sleep(.1)
            result = json.loads((install / 'restarted.json').read_text())
            if not result['pid']:
                raise RuntimeError('Restart probe did not start')
            report_path = install / 'Files/last-update.json'
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not report_path.exists():
                time.sleep(.1)
            if not json.loads(report_path.read_text(encoding='utf-8-sig'))['success']:
                raise RuntimeError('Frozen updater failed')
            print('Real onefile update and independent restart passed.')
            time.sleep(2)  # Allow the restarted bootloader to clean its temporary extraction.
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
