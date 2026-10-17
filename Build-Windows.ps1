param([string]$AutoItDir = "${env:ProgramFiles(x86)}\AutoIt3")
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$check = Join-Path $AutoItDir 'Au3Check.exe'
$compiler = Join-Path $AutoItDir 'Aut2Exe\Aut2exe.exe'
if (!(Test-Path $check) -or !(Test-Path $compiler)) { throw 'Install AutoIt (32 bit), or provide -AutoItDir.' }
& $check '-q' 'GwAu3Bridge.au3'
if ($LASTEXITCODE -ne 0) { throw 'Au3Check failed. Fix the reported errors before building.' }
python -m pip install -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
$env:QT_QPA_PLATFORM = 'offscreen'
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Python tests failed.' }
$version = (python -c 'from version import VERSION; print(VERSION)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not read version.' }
$worker = "Skelefarm-worker-$version.exe"
$bridge = "GwAu3-bridge-$version.exe"
New-Item -ItemType Directory -Path 'dist' -Force | Out-Null
Remove-Item (Join-Path 'dist' $bridge) -ErrorAction SilentlyContinue
$compileArgs = '/in "' + "$PSScriptRoot\GwAu3Bridge.au3" + '" /out "' + "$PSScriptRoot\dist\$bridge" + '" /x86'
$compiled = Start-Process -FilePath $compiler -ArgumentList $compileArgs -Wait -PassThru
if ($compiled.ExitCode -ne 0 -or !(Test-Path (Join-Path 'dist' $bridge))) { throw 'Native bridge compilation failed.' }
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "Skelefarm-worker-$version" --icon assets/skele-taco.ico --paths . --add-binary "dist\$bridge;." worker.py
if ($LASTEXITCODE -ne 0 -or !(Test-Path (Join-Path 'dist' $worker))) { throw 'Python worker build failed.' }
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin --name 'Skelefarm Hub' --icon assets/skele-taco.ico --add-data 'assets;assets' --paths . hub.pyw
if ($LASTEXITCODE -ne 0) { throw 'Hub build failed.' }
Copy-Item README.md, AUDIT.md -Destination dist -Force
$package = Join-Path $PSScriptRoot "SkeleHub-$version-windows.zip"
Compress-Archive -Path 'dist\Skelefarm Hub.exe', (Join-Path 'dist' $worker), 'dist\README.md', 'dist\AUDIT.md' -DestinationPath $package -Force
Write-Host "Ready: $package. Keep the two executables together."
