param(
  [string]$Tag = "bones",
  [string]$Mode = "bones",
  [int]$MaxSeconds = 600,
  [int]$Width = 1600, [int]$Height = 900,
  [string]$Extra = "",
  [string]$World = "worlds/PLHM_EarProTest.ent"
)
# Phaseline ear-pro in-game test: ONE windowed client (Diag) on the PLHM test world with the helmet SNAPSHOT
# (C:\Users\tyler\OneDrive\Desktop\github\OUTLAWHELMETS\SFHELMETS) + PLHM_DevTools. Waits for "[PLHM] DONE"; stops ONLY the process it started.
# HARD RULE: never launches while Tyler's own Reforger / Workbench runs (tyler_guard).
. "C:\Users\tyler\OneDrive\Desktop\SOCOM_TRAINING_MAP\SOURCE\tools\tyler_guard.ps1"
$ClientExe = "C:\Users\tyler\Gaming\steamapps\common\Arma Reforger\ArmaReforgerSteamDiag.exe"
$game = "C:\Users\tyler\Gaming\steamapps\common\Arma Reforger\addons"
$addonsDir = "$game,D:\PhaselineHelmetsTest\deps,C:\Users\tyler\OneDrive\Desktop\github\OUTLAWHELMETS,C:\Users\tyler\OneDrive\Desktop\github\OUTLAWHELMETS\_earpro"
$addonList = "PLHM_DevTools,PhaselineHelmets,PhaselineNightVisionSystems,GMSZAPPrototype"
if (-not (Get-Process steam -ErrorAction SilentlyContinue)) { Start-Process "C:\Users\tyler\Gaming\steam.exe" -ArgumentList "-silent" | Out-Null; Start-Sleep 25 }
$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$out = "D:\PhaselineHelmetsTest\runs\${Tag}_$stamp"
$set = "$out\profile\.save\settings"
New-Item -ItemType Directory -Force $set, "$out\profile\plhmshots" | Out-Null
@"
EngineUserSettings {
 DisplayUserSettings DisplayUserSettings "{60F647F55B116A94}" {
  OverallQuality 4
 }
 PipelineUserSettings PipelineUserSettings "{607B37F35DBA9982}" {
  ShadowQuality High
 }
 ResourceManagerUserSettings ResourceManagerUserSettings "{607B37F35DBA99F6}" {
  TextureDetail 0
 }
 VideoUserSettings VideoUserSettings "{607B37F35DBA99DB}" {
  WindowMode WINDOWED
  ScreenWidth $Width
  ScreenHeight $Height
  ResolutionScale 1
  FsrEnabled 0
  Vsync 0
 }
}
"@ | Set-Content -Encoding ascii "$set\ReforgerEngineSettings.conf"
$a = "-gproj `"C:\Users\tyler\OneDrive\Desktop\github\OUTLAWHELMETS\_earpro\PLHM_DevTools\addon.gproj`" -addonsDir `"$addonsDir`" -addons `"$addonList`" -world `"$World`" -window -screenWidth $Width -screenHeight $Height -posX 0 -posY 0 -forceupdate -nofocus -profile `"$out`" -plhmMode $Mode"
if ($Extra) { $a += " $Extra" }
Wait-TylerIdle "plhm run_client"
"client: $a"
$p = Start-Process -FilePath $ClientExe -ArgumentList $a -WorkingDirectory (Split-Path $ClientExe) -PassThru -WindowStyle Minimized
"pid $($p.Id) out $out"
$p.Id | Set-Content "$out\client_pid.txt"
$t0 = Get-Date; $done = $false; $l = $null
while (((Get-Date) - $t0).TotalSeconds -lt $MaxSeconds) {
  Start-Sleep 4
  if ($p.HasExited) { "CLIENT EXITED (code $($p.ExitCode))"; break }
  $l = Get-ChildItem "$out" -Recurse -Filter console.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1 -Expand FullName
  if ($l -and (Select-String -Path $l -Pattern "\[PLHM\] DONE" -Quiet)) { $done = $true; Start-Sleep 3; break }
}
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }   # only the client this script started
Start-Sleep 2
if ($l) { Copy-Item $l "$out\console.log" -Force; $e = Join-Path (Split-Path $l) "error.log"; if (Test-Path $e) { Copy-Item $e "$out\error.log" -Force } }
"done=$done out=$out"
