# Builds the Android app as an installable APK in apps/mobile/dist. It is signed with the debug key: fine for sideloading
# and the demo, not for the Play Store (make your own keystore for that and keep it out of the repo).
#   powershell -File apps\mobile\scripts\build-apk.ps1                 # phones (arm64) and the emulator (x86_64)
#   powershell -File apps\mobile\scripts\build-apk.ps1 -Abis arm64-v8a # phones only, smaller
# -Workers caps parallel compiles: native C++ builds use a lot of memory next to the model, Docker and an emulator.
param([string]$Abis = "arm64-v8a,x86_64", [int]$Workers = 3)
# Exit codes decide success: Gradle and Expo print warnings on stderr, which "Stop" would turn into fatal errors.
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:NODE_ENV = "production"
# Android Studio's own JDK (21); a newer system JDK can be too new for Gradle.
if (-not $env:JAVA_HOME) { $env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr" }
if (-not $env:ANDROID_HOME) { $env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk" }
$env:CI = "1"
npx expo prebuild -p android --no-install
if ($LASTEXITCODE) { exit $LASTEXITCODE }
Push-Location android
.\gradlew.bat assembleRelease "-PreactNativeArchitectures=$Abis" "--max-workers=$Workers" "-Dorg.gradle.jvmargs=-Xmx2g"
$code = $LASTEXITCODE
Pop-Location
if ($code) { exit $code }
$version = (Get-Content app.json -Raw | ConvertFrom-Json).expo.version
New-Item -ItemType Directory -Force dist | Out-Null
$out = "dist\kairos-$version.apk"
Copy-Item "android\app\build\outputs\apk\release\app-release.apk" $out -Force
"built $out ($([math]::Round((Get-Item $out).Length / 1MB, 1)) MB)"
