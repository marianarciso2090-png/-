param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$backendPath = Join-Path $projectRoot 'backend'
$frontendPath = Join-Path $projectRoot 'frontend'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python was not found. Install Python 3.11 or newer.'
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'Node.js/npm was not found. Install Node.js first.'
}
if (-not (Test-Path $venvPython)) {
    Write-Host 'First run: creating a project-local Python environment...'
    python -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}

Write-Host 'Checking Python dependencies...'
& $venvPython -m pip install --disable-pip-version-check -q -r (Join-Path $backendPath 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install Python dependencies.' }

Push-Location $frontendPath
try {
    if (-not (Test-Path (Join-Path $frontendPath 'node_modules'))) {
        Write-Host 'First run: installing frontend dependencies...'
        npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Could not install frontend dependencies.' }
    }
    Write-Host 'Building the local website...'
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Could not build the frontend.' }
}
finally {
    Pop-Location
}

if (-not $env:DEEPSEEK_API_KEY) {
    throw 'DEEPSEEK_API_KEY is missing. Set it locally and rerun. Do not paste it into chat.'
}
if (-not $env:IFIND_MCP_API_KEY) {
    throw 'IFIND_MCP_API_KEY is missing. Set it locally and rerun. Do not paste it into chat.'
}

$env:APP_ENV = 'local'
$env:DATABASE_URL = 'sqlite:///./local_research.db'
function New-RandomSecret([int]$Length) {
    $bytes = New-Object byte[] $Length
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) }
    finally { $generator.Dispose() }
    return [Convert]::ToBase64String($bytes)
}
$env:SESSION_SECRET = New-RandomSecret 48
if (-not $env:ADMIN_PASSWORD) {
    $env:ADMIN_PASSWORD = New-RandomSecret 18
    Write-Host 'Login username: admin'
    Write-Host "Login password for this run: $env:ADMIN_PASSWORD"
} else {
    Write-Host 'Login username: admin (password from ADMIN_PASSWORD environment variable)'
}

Write-Host "Open in browser: http://127.0.0.1:$Port"
Write-Host 'Press Ctrl+C to stop. Reports are saved in backend/local_research.db.'
Push-Location $backendPath
try {
    & $venvPython -m uvicorn app.local:app --host 127.0.0.1 --port $Port
}
finally {
    Pop-Location
}
