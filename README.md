# ECOBuild
プロジェクト管理ツール

## 導入（Windows）

次のどちらかで導入します。どちらも、足りない Python・git を winget で入れ、ECOBuild を入れて `ecobuild` コマンドを
PATH に通し、最後に `ecobuild init` で初期設定を質問しながら行います。

- **インストーラー**：[`installer/install.cmd`](installer/install.cmd) と [`installer/install.ps1`](installer/install.ps1) を
  同じフォルダに置き、`install.cmd` をダブルクリックします。
- **PowerShell に貼り付けて実行**：

  ```powershell
  & ([scriptblock]::Create([Text.Encoding]::UTF8.GetString((New-Object Net.WebClient).DownloadData('https://raw.githubusercontent.com/superFUKA/ECOBuild/feature/mvp/installer/install.ps1')).TrimStart([char]0xFEFF)))
  ```

終わったら新しい端末を開くと、どのディレクトリからでも `ecobuild <コマンド>` が使えます（`ecobuild --help`）。

### 初期設定（`ecobuild init`）

インストーラーの最後に起動します。後からいつでも実行できます（直っているものは聞きません）。

1. ECOBuild の設定を置くディレクトリ（既定：`%LOCALAPPDATA%\ecobuild`。変えるとユーザーの環境変数 `ECOBUILD_HOME` に保存）
2. 足りないツールの導入（gh、型が使う CMake・C++ コンパイラ等）
3. GitHub へのログイン（`gh auth login`。タスク管理の権限も一緒に）と、git が gh の認証を使う設定
4. git の名前・メール（GitHub のアカウントから候補を出します）
5. `module new`・`module clone`・`module list` で使う既定の所有者（組織名など）

質問せずに準備するには `ecobuild setup`、確かめるだけなら `ecobuild doctor`。

### インストーラーのオプション

| オプション | 内容 |
| --- | --- |
| `-Ref <版>` | 導入する版（ブランチ・タグ・コミット。既定は `feature/mvp`、環境変数 `ECOBUILD_REF` でも指定可） |
| `-Source <ディレクトリ>` | 手元のソースから導入する（開発用。ソースの変更がそのまま反映されます） |
| `-Yes` | 確認せずに進める（`ecobuild init --yes`。GitHub へのログインは行いません） |
| `-NoInit` | `ecobuild init` を起動しない |

更新はインストーラーをもう一度実行するか `pipx upgrade ecobuild`、削除は `pipx uninstall ecobuild` です。

## 導入（Linux）

端末に貼り付けて実行します（[`installer/install.sh`](installer/install.sh)）。足りない git をパッケージマネージャー
（apt-get・dnf・pacman・zypper。sudo を使います）で入れ、[uv](https://docs.astral.sh/uv/) を `~/.local/bin` に入れて、
uv で ECOBuild を入れます。Python 3.11 以上がなければ uv がダウンロードします（システムの Python は変えません）。
最後に `ecobuild init` を起動します（設定の既定の置き場所は `~/.config/ecobuild`）。

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/superFUKA/ECOBuild/feature/mvp/installer/install.sh)"
```

オプションは Windows と同じです（`--ref <版>`・`--source <ディレクトリ>`・`--yes`・`--no-init`。ファイルを落として
`bash install.sh --ref main` のように渡します）。更新はもう一度実行するか `uv tool upgrade ecobuild`、削除は
`uv tool uninstall ecobuild` です。

`ecobuild init`・`ecobuild setup --install` が入れるツール（gh、C++ の CMake・Ninja・g++）は、今は apt-get（Debian・Ubuntu）
だけに対応しています。ほかのディストリビューションでは、表示されたツールを手で入れてください。

## ログ

`ecobuild` は、実行したコマンドで起きたことを、1行に1件の JSON（JSON Lines、日ごとのファイル `YYYY-MM-DD.jsonl`）で残します。不具合を調べるときは、このファイルを AI に渡してください。同じ実行の行には同じ `run` が付きます。

| 置き場所 | 中身 |
| --- | --- |
| モジュールの `.ecobuild/logs/` | そのモジュールで実行したコマンドのすべて（git には見えません） |
| `ECOBUILD_HOME` の `logs/`（既定：`%LOCALAPPDATA%\ecobuild\logs`） | モジュールの外で実行したコマンドのすべてと、モジュールで実行したコマンドの要約（`command.summary`） |

残す量は `ecobuild config set log_level <量>` で変えられます（1回だけなら環境変数 `ECOBUILD_LOG_LEVEL`）。

| 量 | 残すもの |
| --- | --- |
| `debug`（既定） | 下のすべてに加えて、git・gh・CMake・MSBuild 等の外部コマンドの引数・終了コード・出力・所要時間、コマンドの結果 |
| `info` | コマンドの開始・終了（終了コード・所要時間）、進捗、エラー |
| `error` | エラーだけ |
| `off` | 残さない |

C++ のモジュールでは、CppBuild の中の動き（呼んだ API と引数・結果、実行した CMake・MSBuild のコマンドと出力、書いたり消したりしたファイル、構成を省いた理由、トランザクション）も、同じログに `logger` が `cppbuild.` で始まる行として残ります。量は上の表に従い、CppBuild 側の設定は要りません（`debug` のときだけ細かい行まで残ります）。

大きさの上限は `ecobuild config set log_max_mb <MB>`（置き場所ごと、既定 200）。超えたら古い日のファイルから消します。トークン等の秘密は伏せて書きます。

## 構成

ECOBuild はライブラリとして作られ、CLI はその上で動きます。下の層は上の層を知りません。

| 層 | パッケージ | 役割 |
| --- | --- | --- |
| GUI | `gui/` | `ecobuild` コマンドを呼ぶ |
| CLI | `ecobuild_cli` | 本体＋拡張をコマンドで呼ぶ |
| 本体＋拡張 | `ecobuild_bundle` | 同梱の型（`cpp`・`generic`・`python`）を登録した本体。型の既定は `cpp` |
| 拡張 | `ecobuild_cpp`・`ecobuild_generic`・`ecobuild_python` | モジュールの型（`cpp` は CppBuild、`python` は venv・pip・pytest を使う） |
| 本体 | `ecobuild` | モジュール・型の抽象（`ModuleType` と能力）・`Registry` |
| 作業の流れ | `ecowork`・`ecotask` | 作業空間・PR・タスク（git・gh） |

ライブラリとしては、型を `Registry` に登録して `Module` に渡します（外部から型を足せます）。

```python
from ecobuild_bundle import Module      # 同梱の型を使う
from ecobuild_cpp import cpp

module = Module.find(".")
module.build(configuration="Release")
cpp(module).set_pch("Core")             # C++だけの操作は拡張から

from ecobuild import Module as CoreModule, Registry
module = CoreModule.find(".", registry=Registry([MyType]))   # 自分の型を使う
```
