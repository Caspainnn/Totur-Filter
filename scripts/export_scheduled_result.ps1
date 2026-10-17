param([Parameter(Mandatory=$true)][string]$ResultJson)
$ErrorActionPreference = 'Stop'
$tutorProjectRoot = Split-Path -Parent $PSScriptRoot
$tutorResult = $ResultJson | ConvertFrom-Json
if ($tutorResult.status -eq 'OK' -and $tutorResult.report) {
    $tutorSourceReport = [IO.Path]::GetFullPath([string]$tutorResult.report)
    $tutorPrivateRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'WeChatTutorFilter')) + [IO.Path]::DirectorySeparatorChar
    $tutorDestinationReport = Join-Path $tutorProjectRoot 'tutor-report.html'
    if (-not $tutorSourceReport.StartsWith($tutorPrivateRoot, [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($tutorSourceReport) -ne 'report.html') { throw 'Unexpected report source' }
    Move-Item -LiteralPath $tutorSourceReport -Destination $tutorDestinationReport -Force
    $tutorResult.report = $tutorDestinationReport
}
$tutorResult | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $tutorProjectRoot 'scheduled-once-result.json')
