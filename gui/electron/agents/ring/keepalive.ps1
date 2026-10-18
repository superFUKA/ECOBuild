# Ring II への BLE 接続を維持するよう Windows に要求し、接続状態と電池残量を JSON 行で出力する。
# GattSession.MaintainConnection を使う（OS やペアリングの設定は変えない。このプロセスが終われば要求も消える）。
param(
  [Parameter(Mandatory = $true)][string]$Address,   # 例: CCB8F18D6CC0
  [int]$ParentPid = 0,                              # 親（ECOBuild のリングの受信係）が終了したら自分も終わる
  [int]$BatterySeconds = 300
)
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Devices.Bluetooth.BluetoothLEDevice, Windows.Devices.Bluetooth, ContentType = WindowsRuntime]
$null = [Windows.Devices.Bluetooth.GenericAttributeProfile.GattSession, Windows.Devices.Bluetooth, ContentType = WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1

function Await($op, [Type]$type) {
  $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
  if (-not $task.Wait(15000)) { throw 'timeout' }
  $task.Result
}

function Emit($value) {
  [Console]::Out.WriteLine(($value | ConvertTo-Json -Compress))
  [Console]::Out.Flush()
}


# Windows が設定画面用に保持している電池残量（BLE の Battery Service をドライバーが読んだ値）
function Read-Battery {
  $dev = Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like "BTHLE\DEV_$Address*" } | Select-Object -First 1
  if (-not $dev) { return $null }
  $prop = Get-PnpDeviceProperty -InstanceId $dev.InstanceId -KeyName '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2' -ErrorAction SilentlyContinue
  if ($prop -and $prop.Data -ne $null) { [int]$prop.Data } else { $null }
}

$device = $null
$session = $null
$last = $null
$nextBattery = [DateTime]::MinValue

while ($true) {
  if ($ParentPid -and -not (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) { break }
  try {
    if (-not $device) {
      $device = Await ([Windows.Devices.Bluetooth.BluetoothLEDevice]::FromBluetoothAddressAsync([Convert]::ToUInt64($Address, 16))) ([Windows.Devices.Bluetooth.BluetoothLEDevice])
      if (-not $device) { throw 'ペアリング済みのデバイスが見つかりません' }
    }
    # セッションが閉じていたら作り直して維持を要求する（リングが起きたときに Windows が接続し、その後も保つ）
    if (-not $session -or $session.SessionStatus -ne 'Active') {
      if ($session) { $session.Dispose() }
      $session = Await ([Windows.Devices.Bluetooth.GenericAttributeProfile.GattSession]::FromDeviceIdAsync($device.BluetoothDeviceId)) ([Windows.Devices.Bluetooth.GenericAttributeProfile.GattSession])
      $session.MaintainConnection = $true
      # キャッシュを使わずにサービスを問い合わせる。実際の接続が要るので、Windows が能動的にリングへ繋ぎに行く
      try {
        $null = Await ($device.GetGattServicesAsync([Windows.Devices.Bluetooth.BluetoothCacheMode]::Uncached)) ([Windows.Devices.Bluetooth.GenericAttributeProfile.GattDeviceServicesResult])
      } catch { }
    }
    $connected = $device.ConnectionStatus -eq 'Connected'
    $battery = $null
    if ($connected -and [DateTime]::Now -ge $nextBattery) {
      try { $battery = Read-Battery } catch { Emit @{ event = 'error'; message = "battery: $_" } }
      $nextBattery = [DateTime]::Now.AddSeconds($(if ($battery -eq $null) { 30 } else { $BatterySeconds }))
    }
    $state = "$connected/$($session.SessionStatus)"
    if ($state -ne $last -or $battery -ne $null) {
      $out = @{ event = 'ble'; connected = $connected; session = "$($session.SessionStatus)" }
      if ($battery -ne $null) { $out.battery = $battery }
      Emit $out
      $last = $state
    }
    if (-not $connected) { $nextBattery = [DateTime]::MinValue }
  } catch {
    Emit @{ event = 'error'; message = "$_" }
    $device = $null
    $session = $null
    Start-Sleep -Seconds 10
  }
  Start-Sleep -Seconds 3
}
if ($session) { $session.Dispose() }
