$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv-ui\Scripts\python.exe'
$distPath = Join-Path $projectRoot 'frontend\dist\index.html'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Dashboard environment missing. Follow FRONTEND.md to create .venv-ui.'
}
if (-not (Test-Path -LiteralPath $distPath)) {
    throw 'Frontend build missing. Run pnpm build in the frontend folder first.'
}
$address = 'http://127.0.0.1:8011'
try {
    $health = Invoke-RestMethod "$address/health" -TimeoutSec 2
    if ($health.stage -eq 'dashboard') {
        Write-Output "ResistMap is already running at $address"
        exit 0
    }
    throw 'Port 8011 is used by another application.'
} catch {
    if ($_.Exception.Message -like '*used by another*') { throw }
}
$logs = Join-Path $projectRoot 'reports\dashboard'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$env:RESISTMAP_ROOT = $projectRoot
$env:RESISTMAP_AUTH_DB = Join-Path $projectRoot 'data\app\accounts.sqlite3'
$process = Start-Process -FilePath $pythonPath -ArgumentList '-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8011' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'server.log') -RedirectStandardError (Join-Path $logs 'server-error.log') -PassThru
$process.Id | Set-Content (Join-Path $logs 'launcher.pid')
for ($i=0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 300
    try {
        $health = Invoke-RestMethod "$address/health" -TimeoutSec 2
        if ($health.stage -eq 'dashboard') { Write-Output "ResistMap is ready: $address"; exit 0 }
    } catch { }
}
throw "Dashboard did not start. See $logs\server-error.log"
