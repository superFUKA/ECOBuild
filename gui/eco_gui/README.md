# ECOBuild の GUI（GUIFrameWork の上に載せる分）

今の GUI（`gui/app.py`・`gui/static/`・`gui/electron/`）を、[GUIFrameWork](https://github.com/superFUKA/GUIFrameWork) の上に載せ替えていく作業の置き場です。今の GUI は、そのまま動きます。

- 置くのは部品（`parts/`）と画面（`screens/`）だけです。処理は書きません。
- 中継地点が、人が打つのと同じ `ecobuild -C <モジュール> <コマンド> --json` を呼びます。
- ecobuild のコマンドの一覧は、今は自前の形で出るので、`backend.py` が GUIFrameWork の約束の形（CLIFrameWork の構造化出力の形）に直しています。フレームワークの側は ecobuild の形を知りません。
- 表示の CLI（`python -m eco_gui.app <命令>`）で、端末・スクリプト・AI から同じ表示を出せ、今の表示の状況を読めます。

## 動かす

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

## まだ決まっていないこと

- 管理者でないときに、ボタンを灰色にして理由を出す：ECOBuild の CLI に「今できるか」を答える口（`--can`）がない。今は、押すと CLI の誤りが知らせに出る。
- 招待の後に入力欄を空にする・役割の変更（行ごとに選ぶ）：部品とつなぎの作り方を、まだ決めていない。
- 読みが1つずつ順番で遅い（メンバーの画面で数秒）。
- Electron の窓・インストーラーへの組み込み。
