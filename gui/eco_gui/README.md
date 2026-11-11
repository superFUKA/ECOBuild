# ECOBuild の GUI（GUIFrameWork の上に載せる分）

今の GUI（`gui/app.py`・`gui/static/`・`gui/electron/`）を、[GUIFrameWork](https://github.com/superFUKA/GUIFrameWork) の上に載せ替えていく作業の置き場です。今の GUI は、そのまま動きます。

- 置くのは部品（`parts/`）と画面（`screens/`）だけです。処理は書きません。
- 中継地点が、人が打つのと同じ `ecobuild -C <モジュール> <コマンド> --json` を呼びます。
- ecobuild のコマンドの一覧は、今は自前の形で出るので、`backend.py` が GUIFrameWork の約束の形（CLIFrameWork の構造化出力の形）に直しています。フレームワークの側は ecobuild の形を知りません。
- 表示の CLI（`python -m eco_gui.app <命令>`）で、端末・スクリプト・AI から同じ表示を出せ、今の表示の状況を読めます。

## インストーラーで入れる

インストーラー（`ecobuild installer update --ref gui-framework`、または `installer/install.ps1 -Ref gui-framework`）が、専用の venv（`%LOCALAPPDATA%\Programs\ECOBuild GUI Nextenv`）に GUIFrameWork を入れ、デスクトップとスタートメニューに「ECOBuild GUI（新）」を作ります（`gui/eco_gui_setup.py`）。今の「ECOBuild GUI」は、そのまま残ります。

## 窓

Electron が入っていれば（今の GUI のインストーラーが `gui/electron/node_modules` に入れる）、窓はアプリの窓で開きます（`eco_gui/shell.py` と `eco_gui/electron/main.js`。窓を出すだけで、画面も処理も中継地点が受け持つ）。なければ、Edge・Chrome のアドレスバーのない窓で開きます。エージェントと対話する窓は、今の GUI（`gui/electron`）のままです。

## 動かす（開発のとき）

GUIFrameWork を入れた Python で（版は `requirements.txt`）：

```bat
cd gui
python -m eco_gui.app serve --screen hub
```

ダブルクリックで開くなら `gui/ECOBuildGUINext.pyw`（中継地点を裏で起こし、ハブを開く。もう動いていれば、ハブを前に出す）。

ハブの「開く」で、モジュールの窓が開きます。中継地点は1つで、どのモジュールで実行するかは画面の引数 `module`（`ecobuild -C` に渡る）で決まります。

別の端末から：

```bat
python -m eco_gui.app windows --json          :: --json で、機械向けの JSON を1つ
python -m eco_gui.app tree
python -m eco_gui.app run "module members"
python -m eco_gui.app samples                  :: 部品の見本を並べた画面
```

## 移した画面

| 画面 | もとの場所 | 状態 |
|---|---|---|
| `hub`（ハブ） | `static/hub.js` | モジュールの一覧・開く・一覧から外す・一覧に足す・取得・作る・環境チェックを開く。設定（AI・コンテナ・更新）・並べ替え・アーカイブと削除は、まだ |
| `doctor`（環境チェック） | `static/hub.js` の設定 | 道具がそろっているかの一覧。足りないものを入れるボタンは、まだ |
| `menu`（モジュールの窓のメニュー） | `static/module.js` の左のメニュー | 選ぶと、同じ窓で画面が切り替わる。どの画面にも置いてある |
| `overview`（概要） | `static/modinfo.js` のホーム | 名前・型・リポジトリなど。README・ファイルの木は、まだ |
| `workspace`（作業空間） | `static/workspace.js` | 状態・変更を選んでコミット・差分・Push・取り込み・提出・退避と戻す・最近のコミット・ビルド・試験・クリーン（出力を続けて表示）。衝突を直す・構成の選択・退避の一覧は、まだ |
| `files`（ファイル） | `static/explorer.js` | ファイルの木と、選んだファイルのまだコミットしていない変更。足す・動かす（名前を変える）・消す。フォルダーの操作・ドラッグ・複数選択・その場での名前変更は、まだ。一覧は、新しく足した CLI のコマンド `ecobuild files` から読む（今までは GUI のサーバーだけが作っていた） |
| `tasks`（タスク） | `static/tasks.js` | 開いているタスクの一覧・作る・始める・閉じる。ボード・日程・詳細・完了・提出の確認は、まだ |
| `branches`（ブランチ） | `static/branches.js` | 一覧・作る・消す。直接の取り込み・保護・届いている提出は、まだ |
| `history`（履歴） | `static/logview.js` | コミットの一覧と、選んだコミットの中身 |
| `members`（メンバー） | `static/members.js` | 一覧・招待・外す。役割の変更と、管理者でないときの灰色の表示は、まだ |
| `pipelines`（パイプライン） | `static/pipelines.js` | 一覧・足す・流す・消す。タスクの段階への割り当て（`pipeline on`）は、まだ |
| `ci`（CI） | `static/ci.js` | 設定の表示・最近の実行・流す。設定の作成・ログ・秘密の値は、まだ |
| `task`（タスクの詳細） | `static/tasks.js` | 題・本文・状態・コメント。編集（題・段階・優先度・期限・見積もり・担当）・コメント・始める・閉じる・開き直す |
| `board`（ボード） | `static/tasks.js` | 段階ごとの列。段階を変える（計画中・未着手の間だけ。CLI の決まり） |
| `schedule`（日程） | `static/tasks.js` | 予定の帯・次にやる・期限・スプリント・マイルストーン・担当ごとの量（表示だけ） |
| `submissions`・`submission`（提出） | `static/submissions.js`・`prs.js` | 届いている提出・自分の提出。差分・手元で確認・承認・差し戻し・取り下げ・取り込む・反映・取り消し |
| `merge`（取り込み・提出） | `static/branches.js` | ブランチを直接取り込む・提出する・衝突を直すタスクを作る |
| `conflicts`（衝突を直す） | `static/conflicts.js` | 衝突したファイルの一覧と差分。片方の側を採る・続ける・やめる。箇所ごとに直すのは、エディターで |
| `settings`（設定） | `static/modinfo.js` | 全般・ビルド設定・ブランチの保護・管理するファイル・リリース・アカウント・片付け |
| `container`（コンテナ） | `static/modinfo.js` | 状態・入・切・起こす・止める・イメージ・レシピ |
| `hub-settings`・`hub-archive` | `static/hub.js` の設定 | アカウント・全体の設定・AI（ログイン・版）・コンテナのイメージ・ECOBuild の更新・アーカイブと削除 |
| `agents`・`agent-presets`・`pc-agents`（入力の窓は `cfg-agent-add`・`cfg-agent-to-preset`・`cfg-skill-add`・`cfg-skill-to-preset`） | `static/agenteditor.js`・`agentrules.js` | 左に一覧（全エージェント共通 → 役 → スキル）、右に選んだものをその場で直す（部品 `cfg-agent-editor`）。選んだツールの確かめは `ecobuild agent registry fit`。プリセット・Claude Code の版。文書・本文も画面から保存（標準入力で渡す） |
| `operator`（オペレーター） | `static/operator.js` | エージェントの一覧・様子・止める・起こし直す・閉じる・言付け。会話の窓は今の GUI に |
| `help`・`help-guide`（ヘルプ） | `static/help.js` | 使い方の手順と用語、コマンドの一覧と検索（`ecobuild help`） |
| `build`（ビルドと試験） | `static/build.js` | ビルド設定を選ぶ・ビルド・試験（全部・1つ・絞る）・実行・クリーン |
| `stashes`（退避） | `static/workspace.js` | 一覧・退避・選んで戻す・選んで捨てる |
| `blame`（ファイルの記録） | `static/explorer.js` | ファイルの履歴と、行ごとの記録 |
| `cpp`（C++） | `static/explorer.js`・`modinfo.js` | サブプロジェクト・依存先・テンプレート |

## まだ決まっていないこと

- 管理者でないときに、ボタンを灰色にして理由を出す：ECOBuild の CLI に「今できるか」を答える口（`--can`）がない。今は、押すと CLI の誤りが知らせに出る。
- 招待の後に入力欄を空にする・役割の変更（行ごとに選ぶ）：部品とつなぎの作り方を、まだ決めていない。
- 読みが1つずつ順番で遅い（メンバーの画面で数秒）。
- Electron の窓・インストーラーへの組み込み。
