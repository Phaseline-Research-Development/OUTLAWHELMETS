param(
  [int]$Width = 1600, [int]$Height = 900,
  [int]$MaxMinutes = 180,
  [string]$ServerExe = "D:\ArmaReforgerServer\ArmaReforgerServerDiag.exe",
  [string]$ClientExe = "C:\Users\tyler\Gaming\steamapps\common\Arma Reforger\ArmaReforgerSteamDiag.exe"
)
# Phaseline ear-pro MULTIPLAYER DEMO for Tyler: local dedicated server (Diag) + ONE visible client he plays himself.
#   server: -plhmMode mpdemo (PLHM_DevTools PLHM_EarProTest.c) - equips every player (and each respawn) with the SF test
#           helmet + articulated AMP, spawns a box with "Raise / Lower ear protection (left) - me" actions and a dummy
#           soldier that raises / lowers its left cup every 6.5 s. Everything uses the shipping path (service + component).
#   client: -plhmMode idle (the harness does nothing there).
# Lives until Tyler closes the client (or MaxMinutes), then stops the server. Stops ONLY the processes it started.
# HARD RULE: never launches while Tyler's own Reforger / Workbench runs (tyler_guard).
. "C:\Users\tyler\OneDrive\Desktop\SOCOM_TRAINING_MAP\SOURCE\tools\tyler_guard.ps1"
$gproj = "C:\Users\tyler\OneDrive\Desktop\github\OUTLAWHELMETS\_earpro\PLHM_DevTools\addon.gproj"
$addonsDir = "C:\Users\tyler\Gaming\steamapps\common\Arma Reforger\addons,D:\PhaselineHelmetsTest\deps,C:\Users\tyler\OneDrive\Desktop\github\OUTLAWHELMETS,C:\Users\tyler\OneDrive\Desktop\github\OUTLAWHELMETS\_earpro"
$addons = "PLHM_DevTools,PhaselineHelmets,PhaselineNightVisionSystems,GMSZAPPrototype"
if (Test-TylerBusy) { "Tyler's own game / Workbench is running - not launching"; exit 3 }
if (-not (Get-Process steam -ErrorAction SilentlyContinue)) { Start-Process "C:\Users\tyler\Gaming\steam.exe" -ArgumentList "-silent" | Out-Null; Start-Sleep 25 }
$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$out = "D:\PhaselineHelmetsTest\runs\mpdemo_$stamp"
New-Item -ItemType Directory -Force "$out\server", "$out\client\profile\.save\settings" | Out-Null
"run folder: $out"
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
"@ | Set-Content -Encoding ascii "$out\client\profile\.save\settings\ReforgerEngineSettings.conf"

function Log-Of([string]$name) { Get-ChildItem "$out\$name" -Recurse -Filter console.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1 -ExpandProperty FullName }
function Has([string]$name, [string]$pat) { $l = Log-Of $name; return ($l -and (Select-String -Path $l -Pattern $pat -Quiet)) }

$srvArgs = "-gproj=`"$gproj`" -server `"worlds/PLHM_EarProTest.ent`" -addonsDir `"$addonsDir`" -addons `"$addons`" -profile `"$out\server`" -maxFPS 60 -logLevel normal -plhmMode mpdemo"
$srv = Start-Process -FilePath $ServerExe -ArgumentList $srvArgs -WorkingDirectory (Split-Path $ServerExe) -PassThru -WindowStyle Minimized
"server pid $($srv.Id)"
$t0 = Get-Date
$ready = $false
while (((Get-Date) - $t0).TotalSeconds -lt 300) {
  Start-Sleep 3
  if ($srv.HasExited) { "SERVER EXITED code $($srv.ExitCode)"; exit 2 }
  if (Has "server" "Can't compile") { "SERVER SCRIPT COMPILE FAILED"; Stop-Process -Id $srv.Id -Force; exit 4 }
  if (Has "server" "\[MPDEMO\] ready") { $ready = $true; break }
}
"$(Get-Date -Format HH:mm:ss) server ready=$ready after $([int]((Get-Date) - $t0).TotalSeconds) s"
if (-not $ready) { Stop-Process -Id $srv.Id -Force; exit 5 }

$a = "-gproj `"$gproj`" -addonsDir `"$addonsDir`" -addons `"$addons`" -window -posX 0 -posY 0 -screenWidth $Width -screenHeight $Height -forceupdate -client -profile `"$out\client`" -plhmMode idle"
$cl = Start-Process -FilePath $ClientExe -ArgumentList $a -WorkingDirectory (Split-Path $ClientExe) -PassThru
"client pid $($cl.Id)"
"$($srv.Id) $($cl.Id)" | Set-Content "$out\pids.txt"

$t0 = Get-Date
while (((Get-Date) - $t0).TotalMinutes -lt $MaxMinutes) {
  Start-Sleep 5
  if ($srv.HasExited) { "SERVER EXITED code $($srv.ExitCode)"; break }
  if ($cl.HasExited) { "$(Get-Date -Format HH:mm:ss) client closed (code $($cl.ExitCode))"; break }
}
if (-not $cl.HasExited) { Stop-Process -Id $cl.Id -Force }
if (-not $srv.HasExited) { Stop-Process -Id $srv.Id -Force }
Start-Sleep 2
foreach ($n in @("server", "client")) {
  $l = Log-Of $n
  if ($l) { Copy-Item $l "$out\$n.console.log" -Force }
}
"done out=$out"
