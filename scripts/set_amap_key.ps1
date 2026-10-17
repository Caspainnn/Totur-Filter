# Run interactively on the user's own Windows account. Never pass a plaintext key.
param(
    [Security.SecureString]$Key,
    [switch]$Replace
)
$ErrorActionPreference = 'Stop'
$tutorKeyDirectory = Join-Path $env:LOCALAPPDATA 'WeChatTutorFilter'
$tutorKeyPath = Join-Path $tutorKeyDirectory 'amap-key.dpapi'
if ((Test-Path -LiteralPath $tutorKeyPath) -and -not $Replace) {
    throw 'A key already exists for this Windows user. Use -Replace only to replace your own key.'
}
if (-not $Key) { $Key = Read-Host 'Enter your own Amap Web service key (hidden)' -AsSecureString }
$tutorKeyPointer = [IntPtr]::Zero
try {
    $tutorKeyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Key)
    if ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($tutorKeyPointer) -notmatch '\A[a-fA-F0-9]{32}\z') {
        throw 'Expected a 32-character hexadecimal Amap Web service key.'
    }
    New-Item -ItemType Directory -Path $tutorKeyDirectory -Force | Out-Null
    $tutorEncryptedKey = ConvertFrom-SecureString -SecureString $Key
    [IO.File]::WriteAllText($tutorKeyPath, $tutorEncryptedKey, [Text.UTF8Encoding]::new($false))
    Write-Output 'Saved your key using Windows current-user DPAPI. No map request was made.'
} finally {
    if ($tutorKeyPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tutorKeyPointer) }
    $Key.Dispose()
}
