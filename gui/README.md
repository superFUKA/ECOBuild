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
- ハブのモジュールを右クリック（または ⋯）→「ショートカットを作る…」で、選んだフォルダに、そのモジュールの開発環境だけを開くショートカット（「<フォルダ名> - ECOBuild」。中身は `--module <フォルダ>`）を作る（最後に選んだフォルダをこのPCに覚えておく）。開発環境の窓と同じ AppUserModelID を付けるので、ピン留めしたボタンと開いている窓はまとまる。
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

作業空間のロック（`workspace lock／unlock`、`status`・`workspace list` の `lock: {locked, reasons:[{kind: manual|agent|container|command, text, since, pid}]}`。`lock` が無い応答〔古い CLI〕はロックなし扱い）：ロック中は、作業空間のタブに 🔒、上のバーに「ロック中」（押すと理由の一覧・手動ロックを付ける／外す。自動の理由〔エージェント・コンテナ・コマンド〕だけのときは外すボタンを出さず理由だけ）。タスクブランチの切り替え（ブランチのメニュー）・片付け・作業の開始（置く作業空間の選択、`openWorkspace`）は先に止めて理由を出し、返ってきた `workspace_locked` のエラーは理由と外し方の表示にする。非常用の `workspace unlock --force --yes` は使用禁止の位置づけなので、ロックの詳細の中の「非常用の操作」の奥に、強い確認つきで置く。`lock`／`unlock` はビルド等が動いていても待たず（`UNLOCKED`）、実行後に覚えた結果を古くする。自動のロックは GUI の外で増減するので、モジュールの窓は 20 秒ごとに各作業空間の `status` を読み直す。
作業空間の上のバーのアカウント（人の印。作業空間に結び付けていれば緑）：この作業空間で使う GitHub のアカウント（`account show` の `workspace_account`）。押すと、このPCの gh でログインしているアカウント（`account list`）から選んで結び付ける（`account use`）・ほかのアカウント…・結び付けを外す（`account use --clear`）。結び付けると、その作業空間の ecobuild・push・提出・コミットの作者・コンテナの中のエージェントがそのアカウントになる（AI 用のアカウント等）。新しい作業空間の画面でも、ログインしているアカウントが2つ以上なら選べる（`workspace create --account`）。

作業空間の上のバーの「コンテナ」（コンテナにしていれば緑、していなければ「このPC」）：コンテナにする・やめる（`container on/off`）、前もって作る・作り直す・消す（`container start/remove`。当てはまらない操作は出さず、Docker が使えなければ灰色）。動かす・止めるはない（ECOBuild が使うときに動かし、WSL が使わなくなると止める。止まっていても「準備済み」）、このコンテナの設定（`container set`：AI に使わせないもの・使うイメージ）。コンテナの中の AI のログインは、ハブの設定の「AI のログイン（コンテナ用）」（`agent token login/set/status/remove`。トークンは表示しない）。イメージはモジュールごと（`.ecobuild/container/Dockerfile` の環境＋ECOBuild の層）で、ハブの設定の「コンテナのイメージ」（`container image list/build/prune`）で扱う。コンテナにした作業空間では、エージェントはコンテナの中で確認なしに起動し、ビルド・テスト等も中で動く（CLI が渡す。GUI は変わらない）。

## エージェントの窓（Electron だけ。`electron/agents/`）

- 作業空間の「エージェント」は、このアプリの小さな窓のタブで開く（Edge の窓ではコンソール）。タブの端末（node-pty）は `ecobuild -C <場所> agent start --here` を動かす（コンテナの用意・鍵は ecobuild がする。GUI はトークンに触れない）。同じ作業空間のエージェントは1つ（もう一度押すと前に出す）。
- タブ：番号は 1 から続く（閉じると詰める）。ダブルクリックで名前、ドラッグで並べ替え、右クリックで「新しい窓へ」「起動し直す」「続きから起動し直す」（`claude --continue`）「閉じる」。下の線で状態（考え中＝黄の明滅・裏で実行中＝黄・選択肢＝青）。状態は main 側の見えない端末（@xterm/headless）の画面を読む（`screen.js`、`npm test`）。
- 役は3つ：進行役（ユーザーとのやりとりに特化。作業役は直接作らず、話の流れに応じて仕事ごとに管理役を作って命令する。管理役は何人でも）・管理役（1つの仕事を受け持つ。作業役と、大きな部分なら下の管理役を作り、その返答の終わり・報告の知らせを受け取り、要約を上の役へ返す。画面なしで係が動かす）・作業役。エージェントはいつもコンテナの中で起動し、コンテナでない作業空間は起動の前に自動でコンテナにする（`container on`）。モデルの設定は `agent_lead_model`・`agent_manager_model`・`agent_worker_model`（設定がなければ管理役は opus・作業役は sonnet、進行役は Claude Code の既定）。
- 既定の役は進行役：作業空間の記録（member.json）がない作業空間（人が起動するトップ）のエージェントは進行役で、「エージェント」のボタン（既定の起動）も進行役として開く（Claude Code のとき）。進行役は作業役を直接作れず、管理役だけ作れる。
- 進行役と作業役：作業空間の「エージェント」の ▾ の「進行役を起動…」（`agent start --role lead`）は、新しい窓で開き、そのタブは左端に固定（「進」。動かせない）。進行役の `ecobuild agent team start/close/send/list` は、端末の印 `ECOBUILD_AGENT_WINDOW=1`（コンテナの中なら中の印）で、状態の置き場所の `requests/<id>.json` に頼みとして書かれる。それを拾って実行するのは ECOBuild の係（`ecobuild agent serve --json`。main が起動し、終わったら起動し直す）。main は係の出来事に応じるだけ：`agent-start` で作業役をその窓のタブとして開く（`--role worker --prompt …`。下の進行役なら新しい窓）、`agent-stop` で作業役のタブを閉じて `{"ack": <key>}` を係の標準入力に返す（そのあと係が閉じる）。言付け（send）と作業役の返答の終わりの知らせは、係が相手の受け箱（状態の置き場所の `inbox/`）に入れ、main が待機中で入力欄が空のときに貼り付けて送る（`status.take`）。返答の後の `project update` も係がする。
- チーム（AI が起動した作業役）：係が画面なし（アプリ用の起動）で動かす作業役はタブにせず、進行役の窓の「◇ チーム」で見る（`agents/teamui.js`・`teamview.js`、main は `agents/team.js`）。見方は タブ・並べて（格子。クリックで大きく、「戻る」で格子へ）・一覧 の3つで、進行役の作業空間ごとに覚える。様子は `ecobuild -C <進行役> agent team list --nested --recent 3 --json`（チームを出している窓は3秒ごと、出していなければ15秒ごと）、詳しい表示は開いた1人だけ `agent team log <名前> --follow --json`。止まっている・失敗・作業中が長い・10分道具を使っていないものは赤で目立たせる。操作も CLI：止める（`-C <作業役> agent stop`）・起動し直す・閉じる（`agent team restart`・`close`。`ECOBUILD_AGENT_WINDOW=1` で係に頼み、係がアプリ用で起動し直す）・引き取る（`agent team takeover --no-open` の会話を、この窓のタブで開く。閉じると `agent team handback`）・場所を開く。同じ1人は作業空間でつなぐので、起動し直し・引き取り・返しでも表示が続く（出来事は events.jsonl に続けて残る）。閉じた作業役は一覧から消える。作業役の返答の終わりは進行役に届くので、知らせは既定で出さない（⚙ で出せる）。
- 進行役（モジュールのエージェント）：モジュールの左のメニューの「エージェント」（`static/modagent.js`）。タスクは要らない。表示は `agent module status`・会話は進行役の作業空間で `agent conversations`、「進行役と話す」は `agent module prepare`（専用の作業空間を clone・最新に）の後、その場所でエージェントの窓のタブを開く（role `lead`・`module`。窓は進行役の窓で左端に固定「進」。端末では `-C <進行役の作業空間> agent module start --here`）。進行役が作る管理役（親のないタスク）は係がアプリ用で動かし、窓の「◇ チーム」で見る。Docker がない・エージェントの窓がない（ブラウザー）ときは起動を灰色にして理由を出す。片付け（`agent module close`）は、進行役が動いている間・管理役が残っている間は灰色。
- 窓：枠なし。📌 で最前面（常に → 自動 → オフ。自動は返答が届いたときだけ前に出る）。☰（Ctrl+Shift+A）でタブの一覧（状況・最後の出力・入力中の文字）。⚙ で返答の知らせ方（Windows の通知・右下のカードと音・知らせない。音・音量・出しておく時間）。– で最小化すると右下の表示（番号＋名前、縁で状態、返答のバッジ、クリックでのぞき見、⤢ で戻す、ドラッグで動かす）。窓を出すときにフォーカスを奪わない。
- 下のバー：状態・モデル・コンテキスト・使用量の制限の残り（5時間・週）・場所。`agent start --here` が Claude Code に statusLine と Stop フックを渡し、作業空間ごとの置き場所（`ECOBUILD_HOME/agents/status`）に書き出させる。置き場所は端末の出力の見えない印（OSC 1337 `ECOBuildAgentStatus=`）で知る（`status.js`）。
- ハブの左のメニューの下に「リング」「オペレーター」のかんたんな切り替え（丸：緑＝使える、黄＝起動中・登録なし、灰＝使っていない）。リングはエージェントの窓の ⚙ の「リングで操作する」と同じ、オペレーターは裏で動かす・止める。
- オペレーター（番号 0）は裏で常駐（`ecobuild agent operator --here`）。ハブの「オペレーター」は Electron ではこれと話す（会話の記録は main が持つ。選択肢は ↑↓・決定で答える。「タブで開く」で直接やり取り）。作業フォルダーの初めての「信頼するか」には ECOBuild が答える（ECOBuild が作った一式なので）。
- 外からの操作：GUI の操作 `agents`・`agent-open`・`agent-send`・`agent-show`・`agent-close`・`agents-window`・`operator`（`ecobuild gui …`・MCP）。Electron の main は kind が agents の窓としてサーバーの events を待ち受け、タブの様子を知らせ、頼まれた操作をする（`link.js`）。操作の重さ（`actions.py` の effect）は `ecobuild gui --help --json` で名乗り、オペレーターのフックが使う（`agent-send`・`agent-close`・`run` は確認が要る）。
- 音声入力：Claude Code の音声入力（hold モード）を、Space のキーリピートを送ってまねる。🎤 か Ctrl+Alt+V で録音の開始・停止、Ctrl+Alt+↓ で送信（録音中なら止めて、聞き取りが入ってから）、Ctrl+Alt+↑ で消す（録音中なら取り消す）、Ctrl+Alt+← / → で前・次のタブ（ほかのアプリを使っていても効く。ほかのアプリが同じキーを使っていれば効かない）。聞き取り中はタブの線・窓の枠・右下の丸が赤。ハブの「オペレーター」の 🎤 でオペレーターにも（聞き取った文を確かめて「送る」）。コンテナの中のエージェントも使える（コンテナが WSLg の PulseAudio を使う。ecobuild がする）。
- リング（Ring II）：⚙ の「リング」で使う（既定は使わない。ほかのアプリも同じリングを受けていると二重に反応する）。「探す」で識別子（Bluetooth のアドレス）、「操作を登録する」で新しい窓で各操作を3回ずつ（登録表はアプリの設定の場所の `ring-gestures.json`）、リングの LED のモードで信号が変わる操作は「オペレーターモードを登録する」。受信係は `agents/ring/listener.py`（Python の標準ライブラリだけ。Raw Input の受信・ジェスチャーの判定 `gestures.py`・カーソルの保護・接続の維持 `keepalive.ps1`）を Electron の main が子プロセスで動かす（`ring.js`）。常駐（⚙ の「PC にサインインしたときから常駐する」）：スタートアップのショートカットで、窓なしの受信係（`--resident`）がサインインのたびに動き、ECOBuild が閉じている間だけリングでカーソルが飛ぶのを止め、接続を保ち、押し込みで ECOBuild を起動する。ECOBuild が動いているかは、起動のたびに書く `running.pid` で見分ける。設定は `ring-resident.json`（消すと常駐は終わる）。割り当て（agents.json の ring）：作業モード ←→ 前・次のタブ、↑ 消す（空なら最小化・最小化中なら戻す）、↓ 送信、押し込み 音声入力、長押し スクロール、タッチ 右下の返答を閉じる。オペレーターモードは押し込み・↓・↑ がオペレーターへ。選択肢が出ているときに押し込むと選択モード（上下左右で選び、押し込みで決定）。
- 端末の部品（node-pty・@xterm）は `npm install` で入る。インストーラーでは node-pty を asar の外に出す（`asarUnpack`）。

ハブの「オペレーター」：オペレーター（ECOBuild の操作係のエージェント。コードは書かず、ecobuild のコマンドで操作する）との会話。発言ごとに `ecobuild agent ask`（文は標準入力、続きは `--session`）を呼び、返答と実行したコマンドを出す。会話（session と表示している発言）はその窓の localStorage に置くだけ（「新しい会話」で消す）。待つ間も、ほかの操作は止めない（`app.py` の `UNLOCKED`）。返答に実行したコマンドがあれば、モジュールの一覧を読み直す。消す・取り返しのつかない操作は、オペレーターが聞いて「はい」と答えたときだけ実行される（CLI のフックが止める）。

## モジュールの画面

- 「モジュール」はまず「ホーム」：GitHub のリポジトリのページと同じ並び。ファイル構成（エクスプローラーと同じ一覧。フォルダはその場で開く。ダブルクリックで既定のアプリ）と README（Markdown を表示）、横に「このモジュール」（`module show`：GitHub・型・作成元・Project・依存先・場所。届いたら埋める）。
- 「Project」の一覧は、テスト・性能測定を字下げした木（テスト・性能測定は、リンクしているこのモジュールの Project の下。ライブラリ・実行ファイルは何をリンクしていても一番上の段で、main を先頭に。メインが使うものの下に沈まないように。テスト・性能測定の行は上の Project とひとまとまりで、小さく・種類を名前の前に・上の Project へのリンクは省く。名前だけを字下げし、ほかの列はそろえる。兄弟は ├ と └）。`module.html#modinfo/projects` 等でタブを直接開ける。
- モジュールの窓の左の「モジュール」と「設定」の分け方：「モジュール」はモジュールが何で何を持っているか（ホーム・Project・依存。Project・依存先の追加や、Project ごとの設定もここ）、「設定」はモジュール全体をどう作るか（ビルド設定・全般〔main・MSVC のランタイム・ソリューションフォルダー〕・ファイルテンプレート）。「設定」はヘルプと一緒に下に置く（並び替えの対象外）。`module.html#settings/general` 等でタブを直接開ける。
- 役割：アカウントの、このモジュールでの役割は GitHub の権限（`account show`。common.js の `ECO.access`・`isAdmin`・`canTakeIn`・`takeInNote`）。「管理」の操作は管理者だけ、提出の処理（承認・差し戻し・取り込み）は取り込み先のブランチを作った人と管理者だけ（既定のブランチは管理者だけ）。ほかの人には見せて、ボタンを灰色にし、理由をホバーで出す（`.mi button:disabled`）。分からないとき（古い ecobuild 等）は灰色にしない（CLI が止める）。左下のアカウントに役割を出す（`.nav-account-role`）。
- 「ブランチ」（branches.js・submissions.js）：共有ブランチと、そこへ届いている提出をまとめた画面（以前の「管理」の「ブランチ」のタブと、左メニューの「提出」）。共有ブランチ（タスクブランチ以外）を左の縦のタブに並べ（作成元のつながりで字下げ）、そのブランチへ届いている提出の数を出す（タスクの提出は取り込み先 `base`、ブランチ同士の提出は `submitted_to`）。右は、そのブランチ（場所・作成元・作った人〔GitHub の活動の記録〕・自身の提出〔取り込む〕・提出する〔管理者と作った人〕・削除・そこから作ったタスクブランチ）、提出を処理できる人、既定のブランチなら保護（`module protect --show`・設定…・外す。管理者だけが見られる。`--show` は GUI では読むだけとして扱う）。その下に、そのブランチへ届いている提出の一覧・詳細（CI・レビュー・コメント）。ほかの人の提出は手元で確認・差し戻す・承認して取り込む、自分のものは取り込む・取り下げ（タスクを閉じるかは提出のとおり。取り込む画面で変えられる）、ブランチ同士の提出は取り込む。処理できない人には、だれが処理できるかを出す。コマンドはモジュールのフォルダで実行する（手元で確認は、そこで取り出して作業空間へ移る）。提出の表示・ボタンの説明・詳細は作業空間の「提出」と共通（common.js の `submissionText`・`submissionHelp`・`submissionButton`・`submissionDetail`）。詳細と提出の確認の画面には、提出に入るコミット（`task status` の `commits`：作成元にないタスクブランチのコミット）を Push の一覧と同じ形で出す。上の行に「ログ」（すべてのブランチの履歴）・「＋ ブランチ」・「更新」。`--page branches`・`--tab branches`（以前の `#submissions` もここへ）。
- 「管理」：モジュールを管理する画面（管理者だけが変えられる）。中をタブに分ける（「メンバー」「CI」。選んだタブの操作〔CI：GitHub で見る・手動で実行〕はタブの行の右に出る。`--page manage`、`--tab members`・`--tab ci` でそれぞれへ）。「メンバー」のタブ（members.js）：持ち主と共同作業者・招待中の人と役割（`module members`）、招待（`module members add`）・役割の変更（組織のリポジトリだけ。個人のリポジトリは書き込みだけ）・外す（`module members remove`）。一覧は GitHub が管理者にだけ見せるので、ほかの人には理由を出す。「CI」のタブ（ci.js）：上に CI の設定（`ci show`：ワークフローの有無・手で編集したか・今の設定のとおりか、OS・構成・共有ライブラリ・push で動かすブランチ）。「設定を変える…／CIを用意する…」（`ci init`）と「CIをやめる…」（`ci remove`）はワークフローのファイルを書くので、タスクブランチの作業空間を選んで実行する（なければタスク管理へ案内。コミットして提出・取り込むと反映）。中ほどに実行の一覧（`ci status --all`、ブランチで絞ると `--branch`。結果・番号・ブランチ・きっかけ・日時）。行のボタン・右クリックで、失敗した手順のログ（`ci logs --run`）・再実行（`ci rerun`、失敗したジョブだけも）・GitHub で開く。ダブルクリックは失敗ならログ、ほかは GitHub。「手動で実行」はブランチを選んで `ci run --branch`（ワークフローがなければ灰色）。下にシークレット（`ci secret list`・`set`〔値は標準入力で渡す〕・`remove`）。読むのはモジュールのフォルダで。
- 「作業空間」は、このモジュールの作業空間をすべてタブにする（モジュールを作ったときの main の作業空間も）。タスクブランチでは「コミット」「Push」「提出」のタブ（数は変更・未Pushのコミット・提出中なら1。選んだタブはこのPCで覚える）。Push のタブは Push だけ。提出・取り下げは「提出」のタブで行う（ここのタスクブランチのことだけ。提出する前から出る。ボタンは「提出」だけで、取り込まれたらタスクを完了するかは提出の画面のチェックで決める〔外すと中間提出〕。提出済みでも、もう一度「提出」で変えられる。取り込みは見る人の承認か、モジュールの「提出」・タスク管理の「取り込む」。タスクの完了〔提出する変更がない・中間提出の後など〕はタスク管理の「完了にする」＝ task finish --complete。手元で確認している提出なら、その承認・差し戻し。モジュールに届いている提出は「提出」で見る。コミットし終えると Push、Push すると提出のタブへ移る）。タスクブランチでないところでは、これらを出さない（変更はタスクブランチで行うと出る）。
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
