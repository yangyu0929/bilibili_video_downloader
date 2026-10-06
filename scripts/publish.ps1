param([string]$Repository = 'yangyu0929/bilibili_video_downloader', [string]$Version = 'v1.0.0')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$GitHubCli = 'gh'
if (Test-Path -LiteralPath '.tools/gh/bin/gh.exe') {
    $GitHubCli = Join-Path $PWD '.tools/gh/bin/gh.exe'
    $env:GH_CONFIG_DIR = Join-Path $PWD '.tools/gh-config'
}
& $GitHubCli auth status
if ($LASTEXITCODE -ne 0) {
    & $GitHubCli auth login --hostname github.com --git-protocol https --web --skip-ssh-key
    if ($LASTEXITCODE -ne 0) { throw 'GitHub login required.' }
}
& $GitHubCli repo view $Repository --json name > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    & $GitHubCli repo create $Repository --public --description 'Windows Bilibili video downloader with a local browser UI'
    if ($LASTEXITCODE -ne 0) { throw 'Could not create repository.' }
}
git rev-parse --show-toplevel > $null 2>&1
if (-not (Test-Path -LiteralPath '.git')) { throw 'Initialize this project as its own Git repository before publishing.' }
git remote get-url origin > $null 2>&1
if ($LASTEXITCODE -ne 0) { git remote add origin "https://github.com/$Repository.git" }
$ActualRemote = git remote get-url origin
if ($ActualRemote -ne "https://github.com/$Repository.git") { throw "Unexpected remote: $ActualRemote" }
git -c "credential.helper=!`"$GitHubCli`" auth git-credential" push -u origin main
if ($LASTEXITCODE -ne 0) { throw 'Git push failed.' }
git tag --list $Version | Out-Null
git rev-parse -q --verify "refs/tags/$Version" > $null 2>&1
if ($LASTEXITCODE -ne 0) { git tag $Version }
git -c "credential.helper=!`"$GitHubCli`" auth git-credential" push origin $Version
if ($LASTEXITCODE -ne 0) { throw 'Tag push failed.' }
Write-Host "Published source. Windows release build: https://github.com/$Repository/actions"
