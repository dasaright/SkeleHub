param([string]$AutoItDir = "${env:ProgramFiles(x86)}\AutoIt3")
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$check = Join-Path $AutoItDir 'Au3Check.exe'
$compiler = Join-Path $AutoItDir 'Aut2Exe\Aut2exe.exe'
if (!(Test-Path $check) -or !(Test-Path $compiler)) { throw 'Install AutoIt (32 bit), or provide -AutoItDir.' }
& $check '-q' 'Skelefarm.au3'
if ($LASTEXITCODE -ne 0) { throw 'Au3Check failed. Fix the reported errors before building.' }
py -3 -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Python tests failed.' }
$version = (py -3 -c 'from version import VERSION; print(VERSION)').Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not read version.' }
$worker = "Skelefarm-worker-$version.exe"
New-Item -ItemType Directory -Path 'dist' -Force | Out-Null
Remove-Item (Join-Path 'dist' $worker) -ErrorAction SilentlyContinue
$compileArgs = '/in "' + "$PSScriptRoot\Skelefarm.au3" + '" /out "' + "$PSScriptRoot\dist\$worker" + '" /x86'
$compiled = Start-Process -FilePath $compiler -ArgumentList $compileArgs -Wait -PassThru
if ($compiled.ExitCode -ne 0 -or !(Test-Path (Join-Path 'dist' $worker))) { throw 'Worker compilation failed.' }
py -3 -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin --name 'Skelefarm Hub' --paths . hub.pyw
if ($LASTEXITCODE -ne 0) { throw 'Hub build failed.' }
Copy-Item README.md, AUDIT.md -Destination dist -Force
$package = Join-Path $PSScriptRoot "SkeleHub-$version-windows.zip"
Compress-Archive -Path 'dist\Skelefarm Hub.exe', (Join-Path 'dist' $worker), 'dist\README.md', 'dist\AUDIT.md' -DestinationPath $package -Force
Write-Host "Ready: $package. Keep the two executables together."
