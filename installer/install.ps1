<#
.SYNOPSIS
  ECOBuild のインストーラー（Windows）。

.DESCRIPTION
  1. Python 3.11 以上と git がなければ、winget で導入する（確認してから）
  2. pipx を導入し、ECOBuild を GitHub から導入する（ecobuild コマンドが PATH に入る）
  3. ECOBuild GUI を同じ版で導入する（%LOCALAPPDATA%\Programs\ECOBuild GUI。Node.js があれば Electron も入れる。
     デスクトップとスタートメニューにショートカットを作るので、タスクバーにもピン留めできる）
  4. ecobuild init を起動し、質問しながら初期設定を行う
     （設定を置くディレクトリ、gh・ビルドツール、GitHub へのログイン、git の名前・メール、既定の所有者）

  何度実行してもよい（入っているものは入れ直さず、ECOBuild は指定の版に入れ替える）。

.PARAMETER Ref
  導入する ECOBuild の版（ブランチ・タグ・コミット）。既定は環境変数 ECOBUILD_REF、なければ feature/mvp。

.PARAMETER Source
  GitHub ではなく手元のソースから導入する（開発用。ソースの変更がそのまま反映される）。

.PARAMETER Yes
  確認せずに進める（ecobuild init も既定の答えで進める。GitHub へのログインは行わない）。

.PARAMETER NoInit
  ecobuild init を起動しない。

.PARAMETER NoGui
  ECOBuild GUI を導入しない。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install.ps1
.EXAMPLE
  irm https://raw.githubusercontent.com/superFUKA/ECOBuild/feature/mvp/installer/install.ps1 | iex
#>
param(
    [string]$Ref = $(if ($env:ECOBUILD_REF) { $env:ECOBUILD_REF } else { "feature/mvp" }),
    [string]$Source = "",
    [switch]$Yes,
    [switch]$NoInit,
    [switch]$NoGui
)

# 外部のコマンドの失敗は終了コードで確かめる（Windows PowerShell 5.1 では標準エラーを例外にしない）
$ErrorActionPreference = "Continue"
$Repository = "https://github.com/superFUKA/ECOBuild"
# Windows の道具（taskkill・robocopy）はフルパスで呼ぶ：PATH の System32 が展開されていない（%SystemRoot%\system32 のまま）
# PC では、名前では見つからない
$System32 = Join-Path $env:SystemRoot "System32"

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Done([string]$Message) { Write-Host "    $Message" -ForegroundColor Green }

function Stop-Install([string]$Message) {
    Write-Host "エラー：$Message" -ForegroundColor Red
    exit 1
}

function Confirm-Step([string]$Question) {
    if ($Yes) { return $true }
    $answer = Read-Host "$Question [Y/n]"
    return ($answer -eq "" -or $answer -match '^[yYはい]')
}

function Update-SessionPath {
    # 導入したツールを、このウィンドウの中でも使えるようにする
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user;$env:Path"
}

function Install-WithWinget([string]$Id, [string]$Name) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Stop-Install "$Name がありません。winget もないため、$Name を手で導入してから、もう一度実行してください。"
    }
    if (-not (Confirm-Step "$Name がありません。winget で導入しますか？")) {
        Stop-Install "$Name が必要です。導入してから、もう一度実行してください。"
    }
    winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Stop-Install "$Name の導入に失敗しました（winget の終了コード $LASTEXITCODE）。" }
    Update-SessionPath
    Write-Done "$Name を導入しました"
}

function Find-Python {
    # Python 3.11 以上を探す（py ランチャー、python の順。Microsoft Store の入口だけのものは除く）
    foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
        if (-not (Get-Command $candidate[0] -ErrorAction SilentlyContinue)) { continue }
        $rest = @($candidate | Select-Object -Skip 1)
        & $candidate[0] @rest -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" *> $null
        if ($LASTEXITCODE -eq 0) { return , $candidate }
    }
    return $null
}

function Invoke-Python {
    $rest = @($script:Python | Select-Object -Skip 1)
    & $script:Python[0] @rest @args
}

if ($env:OS -ne "Windows_NT") { Stop-Install "このインストーラーは Windows 用です。" }
Write-Host "ECOBuild のインストーラー（版：$(if ($Source) { $Source } else { $Ref })）"

# 1. 前提：Python と git（pip が GitHub から取り出すのに git を使う）
Write-Step "Python と git を確かめます"
$script:Python = Find-Python
if ($null -eq $script:Python) {
    Install-WithWinget "Python.Python.3.12" "Python 3.12"
    $script:Python = Find-Python
    if ($null -eq $script:Python) { Stop-Install "Python を導入しましたが見つかりません。新しい端末を開いて、もう一度実行してください。" }
}
Write-Done ("Python：" + (Invoke-Python --version))
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Install-WithWinget "Git.Git" "git" }
Write-Done ("git：" + (git --version))

# 2. pipx と ECOBuild
Write-Step "pipx を確かめます"
Invoke-Python -m pipx --version *> $null
if ($LASTEXITCODE -ne 0) {
    Invoke-Python -m pip install --user --upgrade --quiet --no-warn-script-location --disable-pip-version-check pipx
    if ($LASTEXITCODE -ne 0) { Stop-Install "pipx の導入に失敗しました。" }
    Write-Done "pipx を導入しました"
}
Invoke-Python -m pipx ensurepath *> $null   # pipx が入れるコマンドの場所を、ユーザーの PATH に足す
Update-SessionPath

# 入っている ecobuild の入れ元・版・依存（JSON。入っていなければ空）。venv の Python で調べる
$ProbeCode = @'
import json
from importlib.metadata import PackageNotFoundError, distribution
try:
    d = distribution("ecobuild")
except PackageNotFoundError:
    raise SystemExit(0)
url = json.loads(d.read_text("direct_url.json") or "{}")
print(json.dumps({"url": url.get("url", ""), "ref": url.get("vcs_info", {}).get("requested_revision", ""),
                  "requires": sorted(d.requires or [])}))
'@
function Get-Installed([string]$VenvPython) {
    $probe = Join-Path ([IO.Path]::GetTempPath()) ("ecobuild-probe-" + [Guid]::NewGuid().ToString("N") + ".py")
    Set-Content -Path $probe -Value $ProbeCode -Encoding ASCII
    $text = & $VenvPython $probe 2>$null
    Remove-Item -Force $probe -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0 -or -not $text) { return $null }
    return ($text | Out-String | ConvertFrom-Json)
}

# 更新を速く：同じ入れ元・版で入っていれば、venv を作り直さず ecobuild だけを入れ替える（pipx install --force は
# 名前を調べるための仮の導入と、venv・依存の作り直しで倍ほどかかる）。版の番号が同じでも入れ替わるよう --force-reinstall、
# 依存は --no-deps で触らない。入れ替えた ecobuild が求める依存が前と違えば（CppBuild の版が上がった等）、
# pip は版の番号が同じ依存を入れ直さないので、いつもの pipx install --force で全部を入れ直す。
function Update-InPlace {
    $venvs = (Invoke-Python -m pipx environment --value PIPX_LOCAL_VENVS 2>$null | Out-String).Trim()
    if (-not $venvs) { return $false }
    $venvPython = Join-Path $venvs "ecobuild\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) { return $false }
    $before = Get-Installed $venvPython
    if ($null -eq $before -or $before.url -ne $Repository -or $before.ref -ne $Ref) { return $false }
    & $venvPython -m pip install --quiet --disable-pip-version-check --force-reinstall --no-deps "ecobuild @ git+$Repository@$Ref" | Out-Host   # 出力を戻り値にしない
    if ($LASTEXITCODE -ne 0) { return $false }
    $after = Get-Installed $venvPython
    if ($null -eq $after -or (($before.requires -join "`n") -ne ($after.requires -join "`n"))) {
        Write-Host "    依存が変わったので、全部を入れ直します"
        return $false
    }
    return $true
}

# 動いている ecobuild（agent token login の窓・別の端末等）があると、ecobuild.exe を置き換えられない（WinError 32）。
# 閉じられるまで待つ（更新を始めた ecobuild 自身は、この窓が始まる前に終わっている）。-Yes では待たずに止める
function Get-RunningEcobuild {
    $venvs = (Invoke-Python -m pipx environment --value PIPX_LOCAL_VENVS 2>$null | Out-String).Trim()
    $bin = (Invoke-Python -m pipx environment --value PIPX_BIN_DIR 2>$null | Out-String).Trim()
    if (-not $venvs) { return @() }
    $places = @((Join-Path $venvs "ecobuild") + "\")
    if ($bin) { $places += (Join-Path $bin "ecobuild.exe") }
    return @(Get-CimInstance Win32_Process -Filter "Name='ecobuild.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $path = $_.ExecutablePath; $path -and ($places | Where-Object { $path.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) }) })
}
# 動いている ecobuild が何か（人に分かる言葉で。止めてよいかの目安も）
function Get-EcobuildRole($commandLine) {
    $line = "$commandLine"
    if ($line -match '\bagent\s+serve\b') { return "ECOBuild の係（GUI が起動するもの。止めてかまいません。GUI を起動すると、また動きます）" }
    if ($line -match '\bagent\s+team\b') { return "前の版の、進行役が頼んだチームの操作（作業役を作る等）を待っているもの。止めると、その操作は失敗になります（作業空間の作業は消えません）" }
    if ($line -match '\bagent\s+mcp\b') { return "エージェントのツール（MCP）のサーバー。止めると、そのエージェントが ECOBuild のツールを使えなくなります（エージェントを起動し直すと戻ります）" }
    if ($line -match '\bagent\s+(start|operator)\b') { return "エージェント（Claude Code）を動かしているもの。止めると、そのエージェントが終わります" }
    if ($line -match '\bagent\s+token\s+login\b') { return "エージェントのログインの窓" }
    return "ecobuild のコマンド"
}
function Wait-EcobuildClosed {
    # @() で受ける：1つだけだと return の配列がほどけ、CimInstance の .Count は空になる（PowerShell 5.1）
    $running = @(Get-RunningEcobuild)
    if ($running.Count -eq 0) { return }
    Write-Host "    動いている ecobuild があるため、入れ替えられません：" -ForegroundColor Yellow
    foreach ($process in $running) {
        Write-Host ("      ・{0}" -f (Get-EcobuildRole $process.CommandLine))
        Write-Host ("        PID {0}（{1} から）：{2}" -f $process.ProcessId, $process.CreationDate.ToString("HH:mm"), $process.CommandLine) -ForegroundColor DarkGray
    }
    if ($Yes) { Stop-Install "動いている ecobuild を閉じてから、もう一度実行してください。" }
    Write-Host "    閉じると自動で進みます。S キーを押すと、これらを止めて進みます。" -ForegroundColor Yellow
    while (@(Get-RunningEcobuild).Count -gt 0) {
        $pressed = $false
        try { $pressed = [Console]::KeyAvailable -and ([Console]::ReadKey($true).Key -eq 'S') } catch { }   # 入力のない窓では待つだけ
        if ($pressed) {
            foreach ($process in @(Get-RunningEcobuild)) { & (Join-Path $System32 "taskkill.exe") /T /F /PID $process.ProcessId 2>&1 | Out-Null }
            Start-Sleep -Seconds 1
            continue
        }
        Start-Sleep -Milliseconds 300
    }
    Write-Done "閉じられました"
}

# pip が途中で失敗すると、外しかけたものが ~cobuild 等として残る（警告が出続ける）ので消す
function Remove-PartialUninstall {
    $venvs = (Invoke-Python -m pipx environment --value PIPX_LOCAL_VENVS 2>$null | Out-String).Trim()
    if (-not $venvs) { return }
    $sitePackages = Join-Path $venvs "ecobuild\Lib\site-packages"
    if (Test-Path $sitePackages) { Get-ChildItem $sitePackages -Filter "~*" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue }
}

# 入れ替え中の印（このプロセスの番号）：GUI のリングの常駐は、この間 GUI を起動しない（起動すると、GUI が動かす ecobuild が
# ecobuild.exe をふさいで入れ替えが失敗する）。終われば消す。消し損ねても、このプロセスが終われば印は効かない
$Installing = Join-Path $env:LOCALAPPDATA "ecobuild\installing"
New-Item -ItemType Directory -Force (Split-Path $Installing) | Out-Null
Set-Content -Path $Installing -Value $PID -Encoding ascii

function Install-Ecobuild {
    Wait-EcobuildClosed
    Remove-PartialUninstall
    if ($Source) {
        Invoke-Python -m pipx install --force --editable $Source
    } elseif (Update-InPlace) {
        $global:LASTEXITCODE = 0
    } else {
        Invoke-Python -m pipx install --force "git+$Repository@$Ref"
    }
}

Write-Step "ECOBuild を導入します（少し時間がかかります）"
Install-Ecobuild
if ($LASTEXITCODE -ne 0 -and @(Get-RunningEcobuild).Count -gt 0) {
    # 入れ替えの途中で ecobuild が起動され、ecobuild.exe がふさがれた：閉じられるのを待って、もう一度
    Write-Host "    入れ替えの途中で ecobuild が起動されました。閉じてから、もう一度入れ替えます。" -ForegroundColor Yellow
    Install-Ecobuild
}
if ($LASTEXITCODE -ne 0) { Stop-Install "ECOBuild の導入に失敗しました。" }
$bin = (Invoke-Python -m pipx environment --value PIPX_BIN_DIR).Trim()
$ecobuild = Join-Path $bin "ecobuild.exe"
if (-not (Test-Path $ecobuild)) { Stop-Install "ecobuild が見つかりません（$ecobuild）。" }
Write-Done "ECOBuild を導入しました：$ecobuild"

# 3. GUI（ECOBuild のパッケージには入っていないので、リポジトリの gui/ を同じ版で置く）
$GuiDir = Join-Path $env:LOCALAPPDATA "Programs\ECOBuild GUI"
function Install-Gui {
    Write-Step "ECOBuild GUI を導入します"
    if ($Source) {
        # 開発用：手元のソースの gui/ をそのまま使う（変更がそのまま反映される）
        $script:GuiDir = Join-Path (Resolve-Path $Source) "gui"
        if (-not (Test-Path (Join-Path $script:GuiDir "app.py"))) { Stop-Install "GUI が見つかりません（$script:GuiDir）。" }
    } else {
        # 指定の版だけを取り出す（ブランチ・タグ・コミットのどれでも）
        $temp = Join-Path ([IO.Path]::GetTempPath()) ("ecobuild-gui-" + [Guid]::NewGuid().ToString("N"))
        git init --quiet $temp
        git -C $temp fetch --quiet --depth 1 "$Repository" $Ref
        if ($LASTEXITCODE -eq 0) { git -C $temp checkout --quiet FETCH_HEAD }
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $temp "gui\app.py"))) {
            Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
            Stop-Install "GUI を取り出せませんでした（$Repository の $Ref）。"
        }
        # 動いている GUI（Electron）は止める（electron.exe が使用中だと置き換えられない）
        Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($GuiDir, [StringComparison]::OrdinalIgnoreCase) } |
            Stop-Process -Force -ErrorAction SilentlyContinue
        # 入れ替える。Electron 本体（node_modules）は残して、入れ直しの時間を省く
        # 動かなかったとき（見つからない等）は前のコマンドの終了コードが残るので、先に空にしておく
        $global:LASTEXITCODE = $null
        & (Join-Path $System32 "robocopy.exe") (Join-Path $temp "gui") $GuiDir /MIR /XD node_modules __pycache__ tests /NFL /NDL /NJH /NJS /NP | Out-Null
        $copied = if ($null -eq $LASTEXITCODE) { 16 } else { $LASTEXITCODE }
        Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
        if ($copied -ge 8) { Stop-Install "GUI を $GuiDir に置けませんでした（robocopy の終了コード $copied）。" }
    }
    Write-Done "GUI：$script:GuiDir"

    # Electron（アプリの窓）。なければ Edge の窓で開く
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            if (Confirm-Step "GUI をアプリの窓（Electron）で開くには Node.js が要ります。winget で導入しますか？（なしでも Edge の窓で使えます）") {
                winget install --id OpenJS.NodeJS.LTS --exact --silent --accept-package-agreements --accept-source-agreements
                Update-SessionPath
            }
        }
    }
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Write-Host "    Electron を導入します（初回は少し時間がかかります）"
        Push-Location (Join-Path $script:GuiDir "electron")
        npm install --no-audit --no-fund --loglevel=error
        $npmCode = $LASTEXITCODE
        Pop-Location
        if ($npmCode -eq 0) { Write-Done "Electron を導入しました" }
        else { Write-Host "    Electron を導入できませんでした。GUI は Edge の窓で開きます。" -ForegroundColor Yellow }
    } else {
        Write-Host "    Node.js がないので、GUI は Edge の窓で開きます（あとで Node.js を入れて、もう一度実行すると Electron になります）。" -ForegroundColor Yellow
    }

    # ショートカット（デスクトップとスタートメニュー。スタートメニューのものはタスクバーにピン留めできる）
    Invoke-Python (Join-Path $script:GuiDir "app.py") --shortcut
    if ($LASTEXITCODE -ne 0) { Stop-Install "GUI のショートカットを作れませんでした。" }
}
if (-not $NoGui) { Install-Gui }

# 4. 初期設定
if (-not $NoInit) {
    Write-Step "初期設定（ecobuild init）"
    if ($Yes) { & $ecobuild init --yes } else { & $ecobuild init }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "初期設定は途中です。あとで ecobuild init を実行すると続きから行えます。" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "完了しました。新しく開いた端末では、どのディレクトリからでも ecobuild が使えます（ecobuild --help）。" -ForegroundColor Green
if (-not $NoGui) {
    Write-Host "GUI：スタートメニューまたはデスクトップの「ECOBuild GUI」（スタートメニューで右クリック →「タスク バーにピン留めする」）。" -ForegroundColor Green
}
Write-Host "更新：ecobuild installer update（またはこのインストーラーをもう一度実行。ECOBuild も GUI も入れ替わります）。"
Write-Host "入っているもの：ecobuild installer show。あとから入れる：ecobuild installer add docker（Docker）・tools（足りないツール）。"
Write-Host "削除：pipx uninstall ecobuild。GUI は $GuiDir と、デスクトップ・スタートメニューの「ECOBuild GUI」を消す。"
Remove-Item $Installing -ErrorAction SilentlyContinue
exit 0   # うまくいった（ecobuild installer update は終了コードで、窓を閉じるか待つかを決める）
