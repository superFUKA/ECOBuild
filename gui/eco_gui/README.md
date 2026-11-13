# ECOBuild の GUI（GUIFrameWork の上に載せる分）

今の GUI（`gui/app.py`・`gui/static/`・`gui/electron/`）を、[GUIFrameWork](https://github.com/superFUKA/GUIFrameWork) の上に載せ替えていく作業の置き場です。今の GUI は、そのまま動きます。

- 置くのは部品（`parts/`）と画面（`screens/`）だけです。処理は書きません。
- 中継地点が、人が打つのと同じ `ecobuild -C <モジュール> <コマンド> --json` を呼びます。
- ecobuild のコマンドの一覧は、今は自前の形で出るので、`backend.py` が GUIFrameWork の約束の形（CLIFrameWork の構造化出力の形）に直しています。フレームワークの側は ecobuild の形を知りません。
- 表示の CLI（`python -m eco_gui.app <命令>`）で、端末・スクリプト・AI から同じ表示を出せ、今の表示の状況を読めます。

## インストーラーで入れる

インストーラー（`ecobuild installer update --ref gui-framework`、または `installer/install.ps1 -Ref gui-framework`）が、専用の venv（`%LOCALAPPDATA%\Programs\ECOBuild GUI Nextenv`）に GUIFrameWork を入れ、デスクトップとスタートメニューに「ECOBuild GUI」を作ります（`gui/eco_gui_setup.py`）。今までの GUI は「ECOBuild GUI（旧）」で開けます。

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
| `hub`（ハブ）・`hub-menu`・`hub-add`・`hub-forget`・`hub-unusable`・`hub-delete`・`hub-account`・`hub-help` | `static/hub.html`・`hub.js`・`common.js` のアカウントの窓 | 左のメニュー（モジュール・オペレーター・設定・ヘルプ、下にアカウント）。モジュールのカード（型ごとの見出し・頭文字・リポジトリ・状態の印・⋯ と右クリックのメニュー・ドラッグで並べ替え）、アーカイブ済み・前の作業空間の折りたたみ、上の帯（環境が足りない・新しい版）、モジュール追加の窓（4つの方法）、アカウントの窓（GitHub で開く・ログイン・切り替え・権限を追加。モジュールの窓の左下からも）。カードのメニューのエクスプローラー・Visual Studio（`ecobuild open`。ソリューションがなければ `frame-vs-build` でビルドしてから）・ショートカット、アーカイブ済み・前の作業空間・使えないモジュールの「フォルダを開く」、追加の窓の「参照…」、登録したフォルダがモジュールでなければ「モジュールにする」を勧める。窓の外のこと（端末・フォルダを選ぶ窓・ショートカット・終了・更新の後の起動し直し）は、この GUI の拡張コマンド `ecobuild gui login・scope・pick-folder・shortcut・quit・update`（`gui/next_commands.py`） |
| `doctor`（環境チェック） | `static/hub.js` の設定 | 確認済み・要対応・任意の3段階と、足りないものの直し方。ハブの設定では、直すボタン（ログイン・権限を追加：`ecobuild gui login`・`gui scope`） |
| `menu`（モジュールの窓のメニュー） | `static/module.js` の左のメニュー | 選ぶと、同じ窓で画面が切り替わる。どの画面にも置いてある |
| `overview`（概要） | `static/modinfo.js` のホーム | 名前・型・リポジトリなど。README・ファイルの木は、まだ |
| `workspace`（作業空間） | `static/workspace.js` | 状態・変更を選んでコミット・差分・Push・取り込み・提出・退避と戻す・最近のコミット・ビルド・試験・クリーン（出力を続けて表示）。衝突を直す・構成の選択・退避の一覧は、まだ |
| `tasks`（タスク管理：一覧） | `static/tasks.js` | 全部の列の表（並べ替え・右クリックのメニュー）、上の帯（表示のタブ・絞り込み）、右に選んだタスクの詳細。表示は6つ：`board`・`tasks`・`task_next`（次にやる）・`schedule`・`task_sprint`（スプリント）・`task_summary`（概要）。入力の窓は `task_new`・`task_start`・`task_edit`・`task_complete`・`task_finish`・`task_drop`・`task_prune`・`task_clean`・`task_assign`・`task_label`・`task_approve`・`task_reject`、人の画面は `task_person` |
| `branches`（ブランチ） | `static/branches.js` | 一覧・作る・消す。直接の取り込み・保護・届いている提出は、まだ |
| `history`（履歴） | `static/logview.js` | コミットの一覧と、選んだコミットの中身 |
| `members`（メンバー） | `static/members.js` | 一覧・招待・外す。役割の変更と、管理者でないときの灰色の表示は、まだ |
| `pipelines`（パイプライン） | `static/pipelines.js` | 一覧・足す・流す・消す。タスクの段階への割り当て（`pipeline on`）は、まだ |
| `ci`（CI） | `static/ci.js` | 設定の表示・最近の実行・流す。設定の作成・ログ・秘密の値は、まだ |
| `task`（タスクの詳細）・`task_pane` | `static/tasks.js` | 番号と段階・状態に合った主ボタン・⋯ メニュー・本文・担当とラベルのチップ・その場で変える計画の値・つながり・作業と提出・コメント。`task_pane` は、表示の右に置くもの |
| `board`（ボード） | `static/tasks.js` | 段階ごとの列（完了は最近の 15 件、削除済みの列）。カードを別の列へ落として、段階を変える・始める・完了にする |
| `schedule`（日程） | `static/tasks.js` | 横の帯（段階の色・遅れ・土日・今日・日程なし。ドラッグで予定を変える・付ける）と、月のカレンダー |
| `submissions`・`submission`（提出） | `static/submissions.js`・`prs.js` | 届いている提出・自分の提出。差分・手元で確認・承認・差し戻し・取り下げ・取り込む・反映・取り消し |
| `merge`（取り込み・提出。カードは `review-branch-merge`、入力の窓は `review-branch-submit`・`review-branch-resolve`・`review-merge`） | `static/branches.js` | ブランチ同士の取り込みのカード（向きの入れ替え・相手のセレクト・確かめ直す・事前確認）・提出する・衝突を直すタスクを作る |
| `conflicts`（衝突を直す） | `static/conflicts.js` | 衝突したファイルの一覧と差分。片方の側を採る・続ける・やめる。箇所ごとに直すのは、エディターで |
| `settings`（設定。入力の窓は `cfg-profile-edit`・`cfg-profile-edit-python`・`cfg-profile-edit-cpp`・`cfg-profile-project`） | `static/modinfo.js` | 全般・ビルド設定（部品 `cfg-profiles`：この PC で使うラジオ・型で変わる列・C++ のオプション・Project ごとの上書き）・ブランチの保護・管理するファイル・リリース・アカウント・片付け |
| `container`（コンテナ） | `static/modinfo.js` | 要約（部品 `cfg-container`：作り方・古い／今の作り方の印・この PC のイメージ・しくみ）・状態・入・切・起こす・止める・イメージ・レシピ |
| `hub-settings` | `static/hub.js` の設定 | タブ：全般（既定の所有者・環境チェック・環境の準備・アカウント・そのほかの設定）・AI（トークン）・エージェント（`pc-agents`）・コンテナ（イメージのまとめ・Claude Code の版）・ECOBuild（版・更新の確かめ・版を選んで入れ直す・この GUI のショートカットと終了）。最後に見ていたタブを覚える（配置 tabs）。更新は新しい版があるときだけ出し、入れ直した後に GUI を起動し直す（`ecobuild gui update`） |
| `agents`・`agent-presets`・`pc-agents`（入力の窓は `cfg-agent-add`・`cfg-agent-to-preset`・`cfg-skill-add`・`cfg-skill-to-preset`） | `static/agenteditor.js`・`agentrules.js` | 左に一覧（全エージェント共通 → 役 → スキル）、右に選んだものをその場で直す（部品 `cfg-agent-editor`）。選んだツールの確かめは `ecobuild agent registry fit`。プリセット・Claude Code の版。文書・本文も画面から保存（標準入力で渡す） |
| `operator`（オペレーター） | `static/operator.js` | エージェントの一覧・様子・止める・起こし直す・閉じる・言付け。会話の窓は今の GUI に |
| `help`・`help-guide`（ヘルプ） | `static/help.js` | 使い方の手順と用語、コマンドの一覧と検索（`ecobuild help`）。モジュールの窓の `help` は部品 `cfg-help`（手順のコマンドからコマンド一覧へ飛ぶ・用途ごとの見出し・探した文字の印・パンくず・使い方の行のコピー） |
| `build`（ビルドと試験） | `static/build.js` | 構成・ビルド設定・実行の対象と引数（部品 `ws-build-setting`）、ビルド・リビルド・クリーン・提出前の確認・実行・テスト、テストを選ぶ木、結果の要約つきの出力 |
| `stashes`（退避の一覧） | `static/workspace.js` | このブランチの退避（番号ごとに戻す・削除）と、ほかのブランチの退避の数（部品 `ws-stashes`） |
| `blame`（注釈履歴） | `static/explorer.js` | 行ごとの、最後に変えたコミット（部品 `ws-blame`）。コミットの変更・ファイルのログを開く |
| `cpp`（Project・依存先。入力の窓は `mod-cpp-…`） | `static/modinfo.js` | Project の木・依存先の状態と依存関係の図・全般・ファイルテンプレート（部品 `mod-cpp`） |

## まだ決まっていないこと

- 管理者でないときに、ボタンを灰色にして理由を出す：ECOBuild の CLI に「今できるか」を答える口（`--can`）がない。今は、押すと CLI の誤りが知らせに出る。
- 招待の後に入力欄を空にする・役割の変更（行ごとに選ぶ）：部品とつなぎの作り方を、まだ決めていない。
- 読みが1つずつ順番で遅い（メンバーの画面で数秒）。
- Electron の窓・インストーラーへの組み込み。
