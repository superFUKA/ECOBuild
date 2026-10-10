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
5. `new`・`clone` で使う既定の所有者（組織名など）

質問せずに準備するには `ecobuild setup`、確かめるだけなら `ecobuild doctor`。

### インストーラーのオプション

| オプション | 内容 |
| --- | --- |
| `-Ref <版>` | 導入する版（ブランチ・タグ・コミット。既定は `feature/mvp`、環境変数 `ECOBUILD_REF` でも指定可） |
| `-Source <ディレクトリ>` | 手元のソースから導入する（開発用。ソースの変更がそのまま反映されます） |
| `-Yes` | 確認せずに進める（`ecobuild init --yes`。GitHub へのログインは行いません） |
| `-NoInit` | `ecobuild init` を起動しない |

更新はインストーラーをもう一度実行するか `pipx upgrade ecobuild`、削除は `pipx uninstall ecobuild` です。
