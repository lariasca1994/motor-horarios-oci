# Levanta el entorno local sin Docker: motor (8001), API (8000) y frontend (8080).
# Requisitos: .venv creado e instalado, y local/.env generado por local/crear_bd.py
#   powershell -ExecutionPolicy Bypass -File local\iniciar.ps1
# Ctrl+C detiene los tres procesos.

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$python = Join-Path $raiz ".venv\Scripts\python.exe"
$envFile = Join-Path $PSScriptRoot ".env"

if (-not (Test-Path $python)) { throw "No existe .venv. Ejecuta: python -m venv .venv; .venv\Scripts\pip install -r functions\api\requirements.txt -r functions\motor\requirements.txt" }
if (-not (Test-Path $envFile)) { throw "No existe local\.env. Ejecuta primero: .venv\Scripts\python local\crear_bd.py" }

foreach ($linea in Get-Content $envFile) {
    if ($linea -match '^\s*([A-Z_]+)\s*=\s*(.*)$') { Set-Item "env:$($Matches[1])" $Matches[2] }
}
$env:MOTOR_MODE = "http"
$env:MOTOR_URL = "http://127.0.0.1:8001/"
$env:CORS_ORIGINS = "http://localhost:8080,http://127.0.0.1:8080"
$env:PYTHONUNBUFFERED = "1"

$procesos = @(
    Start-Process $python -ArgumentList "local_server.py" -WorkingDirectory "$raiz\functions\motor" -NoNewWindow -PassThru
    Start-Process $python -ArgumentList "-m uvicorn main:app --host 127.0.0.1 --port 8000" -WorkingDirectory "$raiz\functions\api" -NoNewWindow -PassThru
    Start-Process $python -ArgumentList "-m http.server 8080 --bind 127.0.0.1" -WorkingDirectory "$raiz\frontend" -NoNewWindow -PassThru
)

Write-Host ""
Write-Host "Frontend  http://localhost:8080"
Write-Host "API       http://localhost:8000/docs"
Write-Host "Motor     http://localhost:8001/health"
Write-Host "Ctrl+C para detener."
try {
    Wait-Process -Id $procesos.Id
} finally {
    $procesos | Where-Object { -not $_.HasExited } | Stop-Process -Force
}
