# ECOBuild GUI

ECOBuild を画面から使うためのアプリ。ECOBuild の実装（`src/` のパッケージ）とは独立している。ECOBuild のCLIはGUIの存在を知らず、GUIはユーザーのPC環境にある `ecobuild` コマンドを `ecobuild -C <場所> <コマンド> --json` で呼ぶことで動く（ECOBuild のコードは読み込まない）。使うのは Python の標準ライブラリだけ（3.11 以上）。

## 起動

- インストーラー（Setup.exe、または `installer/install.cmd`）で入れたときは、スタートメニュー・デスクトップの「ECOBuild GUI」。
- `gui\ECOBuildGUI.pyw` をダブルクリック（コマンドプロンプトは出ない）。
- または端末で `python C:\ECO\ECOBuild\gui\app.py`（どのフォルダからでも同じ）。

どちらも、GUIの窓を開いて、起動したコマンドはすぐ終わる。窓の出し方は2通り。

### Electron（既定。`electron/` に Electron を入れてあるとき）

- 準備：`cd gui\electron` で `npm install`（一度だけ。`node_modules/` はコミットしない）。
- Electron がこのアプリ専用のサーバー（`app.py --electron`）を子プロセスで動かし、ハブの窓を開く。モジュールの窓も Electron の窓で開く。GitHub などGUI以外のアドレスは既定のブラウザで開く。
- 窓をすべて閉じる、またはハブの設定の「GUIを終了」で、Electron もサーバーもすぐ終わる。
- 2つめの起動は新しく動かさず、動いている方のハブの窓を前に出す。
- モジュールの開発環境の窓は、タスクバーではハブとは別のアプリ（モジュールごとの AppUserModelID `ECOBuild.Module.<場所のハッシュ>`、アイコンは `module.ico`）。ボタンはモジュールごとに分かれ、開いている窓をピン留めすると、そのモジュールを開くボタンになる。中身は同じアプリ・同じサーバーなので、操作も連携（更新・「GUIを終了」で全部の窓が閉じる等）も今までどおり。
- ハブを閉じても開発環境の窓は残る（逆も同じ。最後の窓を閉じるとアプリが終わる）。
- `--module <フォルダか名前>`（`python gui\app.py --module C:\ECO\Calc`）：ハブを開かず、そのモジュールの開発環境の窓だけを開く（開いていれば前に出す）。Electron には `--open-module=<フォルダ>` で渡す。Edge の窓でも同じ。
- Python は `ECOBUILD_GUI_PYTHON`、リポジトリの `.venv`、PATH の python の順に探す（`app.py` から起動したときは、起動した Python）。
- 開発用：F12（または Ctrl+Shift+I）で開発者ツール、F5（または Ctrl+R）で再読み込み。`npm start`（`gui\electron` で）でも起動できる。

### Edge の窓（Electron がないとき、または `--browser`）

窓のない Python（pythonw）でサーバーを裏で動かす。

- Edge があればアドレスバーのない窓で、なければ既定のブラウザで開く。
- すでに動いていれば、それを使って窓だけ開く。GUIが更新された後なら、古いサーバーを止めて新しく起動する。
- GUIの窓をすべて閉じると、約3分後にサーバーも終わる（窓は20秒ごとに連絡する）。すぐ終えるときはハブの設定の「GUIを終了」。
- 裏のサーバーの記録（起動・終了・エラー）は `%APPDATA%\ecobuild-gui\gui.log`。動いているサーバーの情報は同じ場所の `server.json`。
- `ecobuild` は起動するときに探す（PATH、なければ起動した Python と同じ環境（`.venv\Scripts`））。別の場所なら `--ecobuild <パス>`。場所は `-C` で渡すので、起動したフォルダは関係ない。ecobuild を入れ直したら、GUI を終了してから起動し直す。
- ecobuild が `.cmd`／`.bat` のラッパーだと、cmd.exe を通るため改行を含む入力（コミットメッセージ・本文・コメント）が1行目だけになり、`%名前%` が環境変数に置き換わる。設定の画面で注意を出す。`.exe`（pip・pipx 等で入れたもの）なら問題ない。
- `--foreground`：裏で動かさず、その端末でサーバーを動かす（Ctrl+C で終了。開発用）。`--no-browser`：窓を開かない。`--port <番号>`：待ち受けるポート（既定 8765、使われていれば空いているもの）。
- 待ち受けは 127.0.0.1 だけで、起動ごとに合言葉が変わる。

### アイコンとショートカット

- 窓のアイコンは `static/icon.svg`。
- ハブの設定の「ショートカットを作る」で、デスクトップとスタートメニューにアイコン付きの「ECOBuild GUI」を作る（端末からは `python gui\app.py --shortcut`）。
  - 中身は「その時の pythonw で `ECOBuildGUI.pyw` を開く」。gui フォルダや Python を移したら作り直す。
  - スタートメニューに置くと、タスクバーにピン留めもできる（スタートメニューで右クリック →「タスク バーにピン留めする」、または開いている窓のボタンを右クリック）。ショートカットには Electron の窓と同じ AppUserModelID（`ECOBuild.GUI`）を付けるので、ピン留めしたボタンと開いている窓は1つのボタンにまとまる。この ID が付く前に作ったショートカットは作り直す。
- ハブのモジュールを右クリック →「デスクトップにショートカットを作る」で、そのモジュールの開発環境だけを開くショートカット（「<フォルダ名> - ECOBuild」。中身は `--module <フォルダ>`）を作る。開発環境の窓と同じ AppUserModelID を付けるので、ピン留めしたボタンと開いている窓はまとまる。
- ショートカットのアイコン `icon.ico`（ハブ）は `static/icon.svg` から、`module.ico`（開発環境）は `static/module-icon.svg` から作る。アイコンを変えたら `python gui\make_icon.py`（Edge で描く）を実行してコミットする。

## インストーラー（Setup.exe）

利用者向けのふつうのアプリのインストーラー（electron-builder の NSIS。ユーザーごと・管理者の権限なし・「次へ」で進む画面）。作るのは配る側で、`gui\electron` で：

```
python bundle\prepare.py     # 同梱する Python（NuGet の python パッケージ）と、ecobuild・依存・pip の wheel を bundle\out に
npm run dist                 # dist\ECOBuild-GUI-Setup-<版>.exe
```

- 中身：Electron のアプリ（`ECOBuild GUI.exe`）、`resources\gui`（この GUI の .py と static）、`resources\python`（フォルダごと動く Python。venv もある）、`resources\wheels`。
- インストールの最後に `bundle\installer.nsh` → `bundle\install_cli.py install` が、wheel から ecobuild を同梱の Python に入れ、`<入れた場所>in\ecobuild.exe` を置き、`bin` をユーザーの PATH に足す（端末・AI エージェントからも使える。`Scripts` は pip 等もあるので PATH に出さない）。アンインストールで PATH から外す。
- アプリ（`app.isPackaged`）は、同梱の Python でサーバーを動かし、`bin\ecobuild.exe` を使う。`ecobuild gui` から起動したときも、`app.py` はこのアプリの exe を開く（`packaged_app()`）。
- ショートカットの AppUserModelID は `appId`（`ECOBuild.GUI`）で、窓と同じ。
- 初期設定は `ecobuild init` を流さず、ハブが開いたときに `doctor` を見て、足りなければ一覧の上に「はじめに」を出す（「準備する」で設定の環境チェックへ。GitHub へのログイン・権限はそこのボタンから端末の窓で）。
- ECOBuild 自体の更新：ハブが開いたときに `installer update --check` を見て、新しい版があれば一覧の上に出す（設定の「ECOBuild（このGUI）」にも。「更新を確かめる」で確かめ直す）。「更新する」は `installer update`（別の窓のインストーラーが CLI と GUI を入れ直す）。GUI はいったん終了し、インストーラーの窓が閉じたら起動し直す（`relaunch-after`：切り離したプロセスが `installer update` の返す窓のプロセスを待ち、ショートカットと同じ起動をする。インストーラーは、うまくいけば窓を閉じ、失敗なら Enter を待つ）。手元のソースから入れたもの・同梱のインストーラーで入れたもの（更新できない）は何も出さない。
- 署名はしていない（初めて開くと SmartScreen の「Windows によって PC が保護されました」が出る。「詳細情報」→「実行」）。
- `bundle\out`・`bundle\cache`・`dist` はコミットしない。

## GUIが自分で行うこと

`ecobuild` にない手元の処理だけ：ハブの一覧の並び順（`ECOBUILD_GUI_HOME`、既定は `%APPDATA%\ecobuild-gui\gui.json`。一覧そのもの・作業空間は `ecobuild workspace list` の記録）、エクスプローラーのファイルの一覧、フォルダ・空のファイルの作成とファイルの移動・削除（型が `file add`・`file move`・`file remove` を持たないとき：generic 等）、既定のアプリで開く、フォルダの選択、ショートカットの作成、ログイン中のアカウント名（`gh api user`）、既定値と画面の出し分けのための `.ecobuild/ecobuild.toml` の `default_base`・型（`[module]` の `type`）の読み取り、ビルドで作られたソリューション（`build/**/*.sln`、VS 2026 のジェネレーターなら `.slnx`）を Visual Studio で開く（ボタンの右の ▾ で Visual Studio 2026／2022 を選ぶ。既定は 2026）。

## モジュールの型

型によってコマンドが違う（モジュールの中で `ecobuild --help`）ので、画面に出す操作も型に合わせる（`common.js` の `TYPES`）。

- cpp：Project・依存・ファイルテンプレート・Visual Studio で開く・C++ のビルド設定（構成は Debug・Release・RelWithDebInfo・MinSizeRel）。
- python：構成は Debug・Release、ビルド設定は構成と並列の数、新しいファイルで tests/ のテストも作るか選べる。
- generic：構成は Debug・Release、ビルド設定は構成だけ。ファイルの作成・移動・削除は GUI が行う。
- GUI が知らない型：すべての型にあるもの（build・test・run・clean と構成）だけ。

## AI

作業空間の上のバーの「エージェント」で `ecobuild agent start`（作業空間のルートで、エージェントを新しい画面で起動する。待たずに戻る）。▾ で、起動するコマンド（`--agent`。このPCで覚える）・AGENTS.md を作る（`agent init`）・AI向けの作業の手順（`agent guide`）。

## モジュールの画面

- 「モジュール」はまず「ホーム」：GitHub のリポジトリのページと同じ並び。ファイル構成（エクスプローラーと同じ一覧。フォルダはその場で開く。ダブルクリックで既定のアプリ）と README（Markdown を表示）、横に「このモジュール」（`module show`：GitHub・型・作成元・Project・依存先・場所。届いたら埋める）。
- 「Project」の一覧は、テスト・性能測定を字下げした木（テスト・性能測定は、リンクしているこのモジュールの Project の下。ライブラリ・実行ファイルは何をリンクしていても一番上の段で、main を先頭に。メインが使うものの下に沈まないように。テスト・性能測定の行は上の Project とひとまとまりで、小さく・種類を名前の前に・上の Project へのリンクは省く。名前だけを字下げし、ほかの列はそろえる。兄弟は ├ と └）。`module.html#modinfo/projects` 等でタブを直接開ける。
- モジュールの窓の左の「モジュール」と「設定」の分け方：「モジュール」はモジュールが何で何を持っているか（ホーム・Project・依存・ブランチ。Project・依存先の追加や、Project ごとの設定もここ）、「設定」はモジュール全体をどう作るか（ビルド設定・全般〔main・MSVC のランタイム・ソリューションフォルダー〕・ファイルテンプレート）。「設定」はヘルプと一緒に下に置く（並び替えの対象外）。`module.html#settings/general` 等でタブを直接開ける。
- 「作業空間」は、このモジュールの作業空間をすべてタブにする（モジュールを作ったときの main の作業空間も）。タスクブランチでは「コミット」「Push」「提出」のタブ（数は変更・未Pushのコミット・提出の件数。選んだタブはこのPCで覚える）。Push のタブは Push だけ。提出・完了は「提出」のタブで行う（ここのタスクブランチは、提出する前から一覧に出る。コミットし終えると Push、Push すると提出のタブへ移る）。タスクブランチでないところでは、これらを出さない（変更はタスクブランチで行うと出る）。
- 作業空間の上のバーは Visual Studio 風：［構成 ▾］（今の構成・ビルド設定を出し、▾ で構成とこのPCで使うビルド設定を選ぶ）・［🔧 ビルド｜▾ リビルド・クリーン・提出前の確認］・テスト、中央に［▶ 実行｜▾ 対象・実行時の引数］、右にフォルダを開く・エージェント・VS2026（VSで開く）。▶ の ▾ で選ぶProject（既定はすべて）が、実行・ビルド・テストの対象。マークだけのボタンは、重ねると名前（単語）が出る。
- エクスプローラーに、PCのほかの場所のファイル・フォルダを落とすと、落とした先のフォルダ（それ以外は作業空間の一番上）にコピーする（タスクブランチで。同じ名前があれば上書きせず止める。C++ は生成ファイルを最新に：`check --no-build`）。GUIの `import-files`。
- ⋯・▾ のメニューは、外のクリック・Esc・項目を選んだとき・別の窓に移ったときに閉じる（`ECO.menu` と、`<details>` の ⋯：common.js の POPUPS）。
- モジュールの作成・取得中は、`ecobuild` が知らせる経過（標準エラーの行。「GitHubにリポジトリを作成中…」等）を順に出す（`cli` に `progress` の番号を付けると、画面が `progress` で読みに来る）。

## ヘルプ

ハブとモジュールの窓の「ヘルプ」（中身は help.js が両方の空の `<section id="help">` に入れる）。「使い方」は作業の流れ（GUIの場所と、そのとき動くコマンド）と用語。「コマンド一覧」は `ecobuild --help --json`（共通のコマンドと、型ごとのコマンド。説明・引数・オプション）を、目的ごとの見出しに分けて出す（見出しはGUIが決める。知らないコマンドは「その他」）。検索（`/`）・型での絞り込み・説明の中の `ecobuild …` から移動・使い方のコピー。`hub.html#help/commands/task%20start` で開ける。

## 外から操作する（ecobuild gui・MCP）

画面のボタンと、外（端末・AIエージェント）から呼ぶ口は、同じ「GUIの操作」（`actions.py`）を通る。片方にだけある操作はできない（`tests/test_actions.py` が、画面のコードが ecobuild や「開く」を直接頼んでいないこと、呼ぶ名前が一覧にあることを確かめる）。

- `run`：ecobuild のコマンドを、GUIを通して実行する（ボタンが行うことの大半。引数は ecobuild のコマンドそのもの）。変える操作は、開いている画面に「誰が実行したか」付きで知らされ、画面は読み直す。
- GUIにしかない操作：`open`（ハブ・モジュールの窓を開く／移る。画面・タブ・タスク・ヘルプのコマンド）、`folder`、`vs`、`notify`（人への知らせ）。
- 状況を見る（エージェント向け）：`windows`（開いている窓と、表示しているモジュール・画面・タブ・タスク・作業空間）、`activity`（最近の操作）。

外からは：

- `ecobuild gui …`：ecobuild の外部サブコマンド（`ecobuild-gui`。GUIのサーバーが起動のたびに ecobuild と同じフォルダに置く `ecobuild-gui.cmd` が `ecobuild_gui.py` を呼ぶ）。例：`ecobuild gui`（ハブ）、`ecobuild gui -C <場所> task start 12`、`ecobuild gui open ECOSTL --tab projects`、`ecobuild gui windows --json`、`ecobuild gui actions`。GUIが動いていなければ起動する（`ECOBUILD_GUI_HOME` の `server.json` に、動いているサーバーの場所がある）。
- `ecobuild gui mcp`：MCP サーバー（標準入出力）。ツールは `ecobuild`（コマンドの実行）・`ecobuild_commands`（コマンドの一覧）・`gui_open` 等。Claude Code なら `claude mcp add ecobuild-gui -- ecobuild gui mcp`。

画面は、サーバーの `events` を待ち受けて（長いポーリング）、ほかの窓・エージェントが行ったことを表示し、移動・開くの頼みに応える。窓は今表示しているものを `window-state` で知らせる。

## キャッシュ（覚えた結果を先に出す）

GUI全体の方針：stale-while-revalidate（HTTP のキャッシュ、React Query・SWR と同じ考え方）。

- 読むだけの遅いコマンド（`app.py` の `CACHEABLE`：タスクの一覧・状態・次にやる、スプリント・マイルストーン、モジュールの情報・一覧、ブランチ、依存先、ビルド設定、Project 等）は、GUIのサーバーが結果を覚える（場所とコマンドごと。`ECOBUILD_GUI_HOME` の `cache.json`。窓をまたいで共有し、起動し直しても使う。14日より古いもの・400件を超えた分は捨てる）。
- 画面は `ECO.query(場所, 引数, onFresh)`：覚えた結果があればすぐそれを出し、同時に読み直す。新しい結果が違えば `onFresh` で描き直す（入力中の欄があれば描き直さない）。覚えた結果がなければ待つ（今までと同じ）。
- 読み直すとき：覚えた結果が15秒より古い、変える操作の後（サーバーがすべてを「古い」にする）、窓に戻ったとき（最近見たもので古いもの）。同じものを同時に読むときは1回だけ実行する（画面の中でもサーバーでも）。
- 裏で読み直している間は、右下に小さく「更新中」（重ねると何を読んでいるか）。
- モジュールを作った・取得した・登録したときは、モジュールの画面が最初に読むもの（`ECO.prefetch`）をまとめて読んで覚えておく（作成・取得は待つついでに。登録は裏で）。

## 表示を待たせない

GitHubを読むコマンドは秒単位でかかる（目安：`task status` 約8秒、`task list`・`task workload` 約4秒、`status --fetch` 約3秒、`module show` 約2秒、`branch list`・`module list` 約1秒。手元だけのもの（`status`・`project list`・`profile list`・`module settings`・`workspace list` 等）は0.3秒前後）。

- 画面・ダイアログは、それ自身が表示するもの以外を待たずに出す。見出しのタスクの題名など、添えるだけの情報は後から入れる。
- ダイアログの選択肢・候補がGitHubにあるもの（担当者・ブランチ・GitHubのモジュール）は、分かっているものだけで開き、残りはフィールドの `more`（Promise）で開いたダイアログに足す（`ECO.form`）。
- 互いに関係のない読み込みは並べて行う（`Promise.all`）。前の読み込みの終わりを待って次を始めない。
- 一度読んだGitHubの情報（ハブの `module list` 等）があれば、それを使う。
- 待たずに出すと、答えが届いたときに表示が変わってしまうもの（ハブのアーカイブ済みのモジュール）は、前回の答えをこのPCに覚えておき（ブラウザの保存領域。表示のためだけ）、それで先に出す。届いた答えで置き換える。

## 構成

| ファイル | 内容 |
| --- | --- |
| `app.py` | サーバー（画面の配布、`ecobuild` の実行、手元の処理） |
| `electron/` | Electron の窓（`main.js`：サーバーの起動と窓の管理、`preload.js`：画面に Electron の中だと伝える）。`bundle/`：インストーラーに入れる Python・ecobuild |
| `icon.ico`・`make_icon.py`・`static/icon.svg` | アイコン（`.ico` は `.svg` から作る） |
| `static/hub.*` | ハブ：モジュールの一覧・追加、既定の所有者、環境チェック・準備 |
| `static/module.*`・`shell.css` | モジュールの窓：左メニューと作業の場所のタブ |
| `static/modinfo.*` | モジュール：概要（module show）・Project・依存（deps tree の図）・ブランチ。設定：ビルド設定・全般（module settings）・ファイルテンプレート（同じファイルで2つの画面） |
| `static/workspace.*`・`explorer.js`・`prs.js`・`build.js` | 作業空間：エクスプローラー・コミット・PR・ビルド・AI |
| `static/tasks.*` | タスク管理：ダッシュボード（段階ごとのカード。ドラッグで段階を変える）・一覧・次にやる・日程・スプリント・集計・詳細・アカウント |
| `static/common.*` | 共通：`ecobuild` の実行、ダイアログ、通知 |

## 試験

```
C:\ECO\ECOBuild\.venv\Scripts\python -m pytest gui/tests
```
