"""コンテナ › イメージ（Dockerfile）：環境の Dockerfile を書き直し、保存して試しに作る（入力の窓。コンテナの要約の「作業空間で編集」から）。

保存は ecobuild container dockerfile --write -（中身は標準入力。タスクブランチでだけ書ける。ファイルを書くだけで、コミットは作業空間で）。
試しに作るのは ecobuild container image build --workspace <この場所>。
"""

ARGS = {"module": "."}  # 作業空間のフォルダー

SCREEN = {
    "root": "page",
    "window": {"title": "イメージ（Dockerfile）", "width": 820, "height": 760},
    "nodes": [
        {"id": "page", "layout": "column", "children": ["editor", "out"]},
        {"id": "editor", "part": "cfg-dockerfile"},
        {"id": "out", "part": "output"},
    ],
    "bindings": [
        {"read": "container dockerfile", "args": {"module": {"arg": "module"}}, "to": "editor.data"},
        {"read": "container recipe", "args": {"module": {"arg": "module"}}, "to": "editor.layer", "from": "layer"},
        {"value": "dockerfile_saved", "to": "editor.saved"},
        {"on": "editor.save", "run": "container dockerfile", "require": ["write"],
         "args": {"module": {"arg": "module"}, "write": {"payload": "text"}},
         "set": {"dockerfile_saved": {"result": ""}}, "notify": ".ecobuild/container/Dockerfile を保存しました（コミットは作業空間の「コミット」で）。"},
        {"on": "editor.build", "run": "container image build", "args": {"module": {"arg": "module"}, "workspace": {"arg": "module"}},
         "output": "out.lines", "notify": "この Dockerfile のイメージを作りました（もうあれば、作り直しません）。"},
        {"on": "editor.close", "close": True},
    ],
}
