$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$BuildPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $BuildPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create Python environment.' }
}
& $BuildPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Failed to install build dependencies.' }
& $BuildPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& $BuildPython -m PyInstaller --noconfirm --onedir --name BilibiliDownloader --collect-all yt_dlp --copy-metadata qrcode --exclude-module imageio_ffmpeg --add-data 'index.html;.' app.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
& $BuildPython scripts/smoke_windows.py
if ($LASTEXITCODE -ne 0) { throw 'Packaged application smoke test failed.' }
Copy-Item -LiteralPath README.md, LICENSE, THIRD_PARTY_NOTICES.md -Destination dist/BilibiliDownloader
Compress-Archive -Path dist/BilibiliDownloader -DestinationPath dist/BilibiliDownloader-Windows-x64.zip -Force
Write-Host 'Ready: dist/BilibiliDownloader-Windows-x64.zip'
