param(
    [string]$PythonPath,
    [switch]$NoMap
)
$ErrorActionPreference = 'Stop'
$tutorProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $PythonPath) {
    $PythonPath = Join-Path $tutorProjectRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw 'Python not found. Create .venv or provide -PythonPath.'
}
foreach ($name in @('chat_allowlist', 'tutor_preferences', 'tutor_profile')) {
    if (-not (Test-Path -LiteralPath (Join-Path $tutorProjectRoot "config\$name.json"))) {
        throw "Missing config/$name.json. Complete the Skill deployment steps first."
    }
}
Push-Location -LiteralPath $tutorProjectRoot
try {
    $tutorArguments = @('-m', 'src.run_filter')
    if ($NoMap) { $tutorArguments += '--no-map' }
    $tutorRunOutput = & $PythonPath @tutorArguments
    $tutorRunExit = $LASTEXITCODE
    & (Join-Path $PSScriptRoot 'export_scheduled_result.ps1') -ResultJson ($tutorRunOutput -join [Environment]::NewLine)
} finally {
    Pop-Location
}
exit $tutorRunExit
