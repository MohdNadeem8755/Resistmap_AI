param([string]$PythonPath = '', [switch]$OpenBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
if (-not $PythonPath) {
    $candidates = @(
        'D:\AncondaAPP\python.exe',
        (Join-Path $projectRoot '.venv-ui\Scripts\python.exe')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            & $candidate -c "import fastapi, uvicorn, pandas, pyarrow.parquet, joblib, sklearn" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $PythonPath = $candidate
                break
            }
        }
    }
    if (-not $PythonPath) {
        $fallback = 'D:\AncondaAPP\python.exe'
        if (-not (Test-Path -LiteralPath $fallback)) { $fallback = Join-Path $projectRoot '.venv-ui\Scripts\python.exe' }
        throw "No Python environment has all required packages (fastapi, uvicorn, pandas, pyarrow, joblib, sklearn). Run: $fallback -m pip install -r requirements-ui.txt"
    }
}
$distPath = Join-Path $projectRoot 'frontend\dist\index.html'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Dashboard environment missing. Create .venv-ui per FRONTEND.md, or pass -PythonPath with an installed Python environment containing requirements-ui.txt dependencies.'
}
$frontend = Join-Path $projectRoot 'frontend'
$dist = Get-Item -LiteralPath $distPath -ErrorAction SilentlyContinue
$inputs = Get-ChildItem -LiteralPath "$frontend\src","$frontend\public" -Recurse -File
$inputs += Get-Item -LiteralPath "$frontend\index.html","$frontend\vite.config.js","$frontend\package.json","$frontend\pnpm-lock.yaml"
if ((-not $dist -or ($inputs | Where-Object { $_.LastWriteTimeUtc -gt $dist.LastWriteTimeUtc } | Select-Object -First 1)) -and
    (Test-Path -LiteralPath "$frontend\node_modules\.bin\vite.cmd")) {
    Push-Location -LiteralPath $frontend
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed. See the build output above.' }
    } finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath $distPath)) {
    throw 'Frontend build missing. Run pnpm build in the frontend folder first.'
}
$address = 'http://127.0.0.1:8011'
function Show-Dashboard {
    Write-Output "ResistMap: $address"
    if ($OpenBrowser) {
        try { Start-Process $address }
        catch { Write-Warning "Open $address in your browser." }
    }
}
try {
    $health = Invoke-RestMethod "$address/health" -TimeoutSec 2
    if ($health.stage -eq 'dashboard') {
        Show-Dashboard
        exit 0
    }
    throw 'Port 8011 is used by another application.'
} catch {
    if ($_.Exception.Message -like '*used by another*') { throw }
}
$logs = Join-Path $projectRoot 'reports\dashboard'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$env:RESISTMAP_ROOT = $projectRoot
# Keep Anaconda MKL from loading a second OpenMP runtime alongside CTranslate2.
$env:MKL_THREADING_LAYER = 'SEQUENTIAL'
$env:RESISTMAP_AUTH_DB = Join-Path $projectRoot 'data\app\accounts.sqlite3'
$process = Start-Process -FilePath $pythonPath -ArgumentList '-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8011' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'server.log') -RedirectStandardError (Join-Path $logs 'server-error.log') -PassThru
$process.Id | Set-Content (Join-Path $logs 'launcher.pid')
for ($i=0; $i -lt 120; $i++) {
    Start-Sleep -Milliseconds 300
    try {
        $health = Invoke-RestMethod "$address/health" -TimeoutSec 2
        if ($health.stage -eq 'dashboard') { break }
    } catch { }
    if ($process.HasExited) { throw "Dashboard exited. See $logs\server-error.log" }
}
if ($health.stage -ne 'dashboard') { throw "Dashboard did not start. See $logs\server-error.log" }
Show-Dashboard
