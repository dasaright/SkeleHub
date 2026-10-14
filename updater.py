"""Download release packages and hand replacement to a separate Windows process."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from version import VERSION, REPOSITORY, worker_name

API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
MAX_DOWNLOAD = 150 * 1024 * 1024


def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value)
    if not match:
        raise ValueError('Release must use a version such as v0.2.0.')
    return tuple(map(int, match.groups()))


def request(url):
    return urllib.request.Request(url, headers={'User-Agent': f'SkeleHub/{VERSION}', 'Accept': 'application/vnd.github+json'})


def check_release(current=VERSION):
    with urllib.request.urlopen(request(API), timeout=15) as response:
        release = json.load(response)
    tag = release['tag_name']
    if version_tuple(tag) <= version_tuple(current):
        return None
    version = tag.removeprefix('v')
    name = f'SkeleHub-{version}-windows.zip'
    asset = next((a for a in release.get('assets', []) if a['name'] == name), None)
    if not asset:
        raise ValueError(f'{tag} has no Windows package yet.')
    url = asset['browser_download_url']
    prefix = f'https://github.com/{REPOSITORY}/releases/download/'
    if not url.startswith(prefix):
        raise ValueError('Unexpected release download location.')
    return {'version': version, 'url': url, 'digest': asset.get('digest'), 'size': asset.get('size', 0)}


def validate_package(path, version):
    allowed = {'Skelefarm Hub.exe', worker_name(version), 'README.md', 'AUDIT.md'}
    required = {'Skelefarm Hub.exe', worker_name(version)}
    with zipfile.ZipFile(path) as archive:
        names = []
        expanded = 0
        for info in archive.infolist():
            p = PurePosixPath(info.filename)
            if info.is_dir() or len(p.parts) != 1 or p.name not in allowed or '\\' in info.filename:
                raise ValueError('Unexpected file in update package.')
            if p.name in names or info.file_size > MAX_DOWNLOAD:
                raise ValueError('Invalid update package entry.')
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Links are not allowed in update packages.')
            expanded += info.file_size
            names.append(p.name)
        if expanded > MAX_DOWNLOAD or not required.issubset(names):
            raise ValueError('Update package is incomplete or too large.')
        for name in required:
            with archive.open(name) as exe:
                if exe.read(2) != b'MZ':
                    raise ValueError('Update contains an invalid executable.')
        if archive.testzip():
            raise ValueError('Update ZIP is corrupt.')
    return names


def stage_release(release, data_dir, progress=None):
    report = progress or (lambda message: None)
    staging = Path(tempfile.mkdtemp(prefix='update-', dir=data_dir))
    try:
        package = staging / 'package.zip'
        size = 0
        hasher = hashlib.sha256()
        report('Connecting to update download…')
        with urllib.request.urlopen(request(release['url']), timeout=30) as response, package.open('wb') as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_DOWNLOAD:
                    raise ValueError('Update exceeds the maximum size.')
                output.write(chunk)
                hasher.update(chunk)
                total = release.get('size', 0)
                if total:
                    report(f"Downloading v{release['version']}: {min(100, int(size * 100 / total))}% ({size / 1048576:.1f} / {total / 1048576:.1f} MB)")
                else:
                    report(f"Downloading v{release['version']}: {size / 1048576:.1f} MB")
        report('Verifying download size and checksum…')
        digest = release.get('digest')
        if digest and digest != 'sha256:' + hasher.hexdigest():
            raise ValueError('Release checksum does not match.')
        if release.get('size') and release['size'] != size:
            raise ValueError('Download is incomplete.')
        report('Validating update package…')
        names = validate_package(package, release['version'])
        report('Extracting update files…')
        with zipfile.ZipFile(package) as archive:
            for name in names:
                target = staging / name
                with archive.open(name) as src, target.open('wb') as out:
                    shutil.copyfileobj(src, out)
        (staging / 'apply.ps1').write_text(HELPER, encoding='utf-8-sig')
        (staging / 'manifest.json').write_text(json.dumps(names), encoding='utf-8')
        report('Update verified and ready to install.')
        return staging
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def apply_and_restart(staging, install_dir, pid):
    if os.name != 'nt':
        raise RuntimeError('Updates require Windows.')
    # Old workers use versioned filenames, so they remain untouched and running.
    process = subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                      str(staging / 'apply.ps1'), '-HubPid', str(pid),
                      '-InstallDir', str(install_dir), '-StagingDir', str(staging)],
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if (staging / 'ready').is_file():
            return
        if process.poll() is not None:
            (staging / 'cancelled').touch()
            raise RuntimeError('Update helper could not start. See the staged update log.')
        time.sleep(0.1)
    (staging / 'cancelled').touch()
    raise RuntimeError('Update helper did not confirm startup; the hub remains open.')


HELPER = r'''
param([int]$HubPid, [string]$InstallDir, [string]$StagingDir)
$ErrorActionPreference = 'Stop'
$log = Join-Path $StagingDir 'update.log'
$result = Join-Path (Split-Path $StagingDir -Parent) 'last-update.json'
$backups = @{}
$installed = @()
$names = @()
$hubExited = $false
function Replace-WithRetry([string]$Source, [string]$Target) {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        try {
            Copy-Item -LiteralPath $Source -Destination ($Target + '.new') -Force
            Move-Item -LiteralPath ($Target + '.new') -Destination $Target -Force
            return
        } catch {
            if ([DateTime]::UtcNow -ge $deadline) { throw }
            Start-Sleep -Milliseconds 250
        }
    } while ($true)
}
try {
    $names = Get-Content -LiteralPath (Join-Path $StagingDir 'manifest.json') -Raw | ConvertFrom-Json
    foreach ($name in $names) {
        if ([IO.Path]::GetFileName($name) -ne $name) { throw 'Invalid manifest filename' }
    }
    # Acknowledge startup before the GUI exits. Wait only for the hub PID.
    'ready' | Set-Content -LiteralPath (Join-Path $StagingDir 'ready')
    if (Test-Path -LiteralPath (Join-Path $StagingDir 'cancelled')) { throw 'Update handoff cancelled' }
    $hub = Get-Process -Id $HubPid -ErrorAction SilentlyContinue
    if ($hub) { Wait-Process -Id $HubPid -Timeout 60 -ErrorAction Stop }
    if (Test-Path -LiteralPath (Join-Path $StagingDir 'cancelled')) { throw 'Update handoff cancelled' }
    $hubExited = $true
    foreach ($name in $names) {
        $source = Join-Path $StagingDir $name
        if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw 'Staged update file missing' }
        $target = Join-Path $InstallDir $name
        if (Test-Path -LiteralPath $target) {
            $backup = Join-Path $StagingDir ($name + '.backup')
            Copy-Item -LiteralPath $target -Destination $backup -Force
            $backups[$target] = $backup
        }
        # Record before replacement so even a partial failure is rolled back.
        $installed += $target
        Replace-WithRetry $source $target
    }
    Start-Process -FilePath (Join-Path $InstallDir 'Skelefarm Hub.exe') -WorkingDirectory $InstallDir -ErrorAction Stop
    'Update applied; hub restarted.' | Set-Content -LiteralPath $log
    @{ success = $true; message = 'Update applied; hub restarted.'; log = $log } | ConvertTo-Json | Set-Content -LiteralPath $result -Encoding UTF8
} catch {
    $failure = $_
    [array]::Reverse($installed)
    foreach ($target in $installed) {
        try {
            if ($backups.ContainsKey($target)) { Replace-WithRetry $backups[$target] $target }
            else { Remove-Item -LiteralPath $target -ErrorAction SilentlyContinue }
        } catch { 'Rollback failed: ' + $_ | Add-Content -LiteralPath $log }
    }
    foreach ($name in $names) {
        Remove-Item -LiteralPath ((Join-Path $InstallDir $name) + '.new') -ErrorAction SilentlyContinue
    }
    $failure | Out-String | Add-Content -LiteralPath $log
    @{ success = $false; message = 'Update failed; rollback attempted.'; log = $log } | ConvertTo-Json | Set-Content -LiteralPath $result -Encoding UTF8
    $old = Join-Path $InstallDir 'Skelefarm Hub.exe'
    if ($hubExited -and (Test-Path -LiteralPath $old -PathType Leaf)) {
        Start-Process -FilePath $old -WorkingDirectory $InstallDir -ErrorAction SilentlyContinue
    }
}
'''
