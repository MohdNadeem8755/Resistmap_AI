$env:RESISTMAP_ROOT = 'D:\ResistMap-AI'
$env:MKL_THREADING_LAYER = 'SEQUENTIAL'
$env:RESISTMAP_AUTH_DB = 'D:\ResistMap-AI\data\app\accounts.sqlite3'
Set-Location 'D:\ResistMap-AI'
& 'D:\AncondaAPP\python.exe' -m uvicorn backend.main:app --host 127.0.0.1 --port 8011
