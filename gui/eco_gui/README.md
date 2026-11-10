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
set ECOBUILD_GUI_MODULE=C:\path\to\module
python -m eco_gui.app serve --screen overview
```

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
| `menu`（モジュールの窓のメニュー） | `static/module.js` の左のメニュー | 選ぶと、同じ窓で画面が切り替わる。どの画面にも置いてある |
| `overview`（概要） | `static/modinfo.js` のホーム | 名前・型・リポジトリなど。README・ファイルの木は、まだ |
| `tasks`（タスク） | `static/tasks.js` | 開いているタスクの一覧だけ。ボード・日程・作る・始めるは、まだ |
| `members`（メンバー） | `static/members.js` | 一覧・招待・外す。役割の変更と、管理者でないときの灰色の表示は、まだ |
| `pipelines`（パイプライン） | `static/pipelines.js` | 一覧・足す・流す・消す。タスクの段階への割り当て（`pipeline on`）は、まだ |
| `ci`（CI） | `static/ci.js` | 設定の表示・最近の実行・流す。設定の作成・ログ・秘密の値は、まだ |

## まだ決まっていないこと

- 管理者でないときに、ボタンを灰色にして理由を出す：ECOBuild の CLI に「今できるか」を答える口（`--can`）がない。今は、押すと CLI の誤りが知らせに出る。
- 招待の後に入力欄を空にする・役割の変更（行ごとに選ぶ）：部品とつなぎの作り方を、まだ決めていない。
- 読みが1つずつ順番で遅い（メンバーの画面で数秒）。
- Electron の窓・インストーラーへの組み込み。
