$ErrorActionPreference = "Stop"

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location $Root
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$Version = (& $Python -c "from flashcmd_version import __version__; print(__version__)").Trim()
if ($LASTEXITCODE -ne 0 -or $Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Could not read a valid FlashCMD version."
}
$WixCommandInfo = Get-Command wix -ErrorAction SilentlyContinue
$WixCommand = if ($WixCommandInfo) { $WixCommandInfo.Source } else { $null }
if (-not $WixCommand) {
    $WixGlobalTool = Join-Path $env:USERPROFILE ".dotnet\tools\wix.exe"
    if (Test-Path -LiteralPath $WixGlobalTool -PathType Leaf) {
        $WixCommand = $WixGlobalTool
    } else {
        throw "WiX v4 is required for the MSI. Install it with: dotnet tool install --global wix --version `"4.*`""
    }
}

$Portable = Join-Path $Root "release\FlashCMD-$Version-windows-x64.exe"
$Msi = Join-Path $Root "release\FlashCMD-$Version-windows-x64.msi"
$DistExe = Join-Path $Root "dist\FlashCMD.exe"

function Remove-GeneratedPath([string]$Path) {
    $Full = [IO.Path]::GetFullPath($Path)
    $Allowed = @(
        [IO.Path]::GetFullPath((Join-Path $Root "build")),
        [IO.Path]::GetFullPath((Join-Path $Root "dist")),
        [IO.Path]::GetFullPath($Portable),
        [IO.Path]::GetFullPath($Msi)
    )
    if ($Full -notin $Allowed) { throw "Refusing to remove unexpected path: $Full" }
    if (Test-Path -LiteralPath $Full) { Remove-Item -LiteralPath $Full -Recurse -Force }
}

& $PSScriptRoot\test.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Remove-GeneratedPath (Join-Path $Root "build")
Remove-GeneratedPath (Join-Path $Root "dist")
Remove-GeneratedPath $Portable
Remove-GeneratedPath $Msi
New-Item -ItemType Directory -Force -Path (Join-Path $Root "release") | Out-Null

& $Python -m PyInstaller --clean --noconfirm packaging\flashcmd-windows.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path -LiteralPath $DistExe -PathType Leaf)) {
    throw "PyInstaller did not create $DistExe"
}
$VersionInfo = (Get-Item -LiteralPath $DistExe).VersionInfo
if ($VersionInfo.ProductName -ne "FlashCMD" -or $VersionInfo.ProductVersion -ne $Version) {
    throw "Packaged metadata mismatch: $($VersionInfo.ProductName) $($VersionInfo.ProductVersion)"
}
$SmokeProcess = Start-Process -FilePath $DistExe -ArgumentList "--version" -Wait -PassThru
if ($SmokeProcess.ExitCode -ne 0) {
    throw "Packaged version startup smoke test failed with exit code $($SmokeProcess.ExitCode)."
}

$SigningEnabled = $env:FLASHCMD_WINDOWS_CERT_THUMBPRINT -and $env:FLASHCMD_WINDOWS_TIMESTAMP_URL
if ($SigningEnabled) {
    if (-not (Get-Command signtool -ErrorAction SilentlyContinue)) { throw "signtool is required for signing." }
    & signtool sign /sha1 $env:FLASHCMD_WINDOWS_CERT_THUMBPRINT /fd SHA256 `
        /tr $env:FLASHCMD_WINDOWS_TIMESTAMP_URL /td SHA256 $DistExe
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "Windows signing configuration is incomplete; building unsigned artifacts."
}

Copy-Item -LiteralPath $DistExe -Destination $Portable
& $WixCommand build installer\windows\FlashCmd.wxs -arch x64 `
    -ext WixToolset.UI.wixext -ext WixToolset.Util.wixext `
    -d "ProductVersion=$Version" -d "SourceExe=$DistExe" -o $Msi
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($SigningEnabled) {
    & signtool sign /sha1 $env:FLASHCMD_WINDOWS_CERT_THUMBPRINT /fd SHA256 `
        /tr $env:FLASHCMD_WINDOWS_TIMESTAMP_URL /td SHA256 $Msi
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& $WixCommand msi validate $Msi
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Built $Portable"
Write-Host "Built $Msi"
