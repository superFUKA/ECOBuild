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

## 構成

ECOBuild はライブラリとして作られ、CLI はその上で動きます。下の層は上の層を知りません（`tests/unit/test_layers.py` で確かめています）。

| 層 | パッケージ | 役割 |
| --- | --- | --- |
| GUI | `gui/` | `ecobuild` コマンドを呼ぶ |
| CLI | `ecobuild_cli` | 本体＋拡張をコマンドで呼ぶ。TortoiseGit の画面もここ |
| 本体＋拡張 | `ecobuild_bundle` | 同梱の型（`cpp`・`generic`）を登録した本体（型の既定は `cpp`）と、このPCの準備（`doctor`・`setup`・`init`） |
| 拡張 | `ecobuild_cpp`・`ecobuild_generic` | モジュールの型（`cpp` は CppBuild を使う） |
| 本体 | `ecobuild` | モジュール・型の抽象（`ModuleType` と能力）・`Registry`・このPCの設定（`settings`） |
| 作業の流れ | `ecowork` | 作業空間・提出・最新化・CI（git・gh）。本体はタスクも含めて ecowork から使う |
| タスク管理 | `ecotask` | GitHub をデータベースとして使うタスク管理（gh） |

ライブラリとしては、型を `Registry` に登録して `Module` に渡します（外部から型を足せます）。
作業の流れ（タスク・提出・CI 等）は `module.repository`（`ecowork.Repository`）を直接使います。
`Module` が持つのは、型・管理するファイル・確認が関わる操作（`commit`・`submit`・`finish`・`sync` 等）です。

```python
from ecobuild_bundle import Module      # 同梱の型を使う
from ecobuild_cpp import cpp

module = Module.find(".")
module.build(configuration="Release")
cpp(module).set_pch("Core")             # C++だけの操作は拡張から
module.repository.create_task("Vector を作る").start()   # 作業の流れは ecowork から

from ecobuild import Module as CoreModule, Registry
module = CoreModule.find(".", registry=Registry([MyType]))   # 自分の型を使う
```

エラーのヒントに書く操作の名前は作業の流れの言葉（`task commit` 等）で、プログラム名は `Module.command`
（CLI は `ecobuild`、ライブラリの既定は空）で決まります。
