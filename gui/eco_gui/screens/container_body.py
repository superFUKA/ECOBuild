"""コンテナの中身：この作業空間のコンテナの状態・設定と、イメージの作り方。設定のタブ（settings）と、コンテナのページ（container）に置く。"""

ARGS = {"module": "."}  # モジュール（作業空間）のフォルダー

SCREEN = {
    "root": "box",
    "nodes": [
        {"id": "box", "layout": "column", "children": ["summary", "tabs"]},
        # 要約：環境の作り方・イメージ・この作業空間のコンテナ（古い／今の作り方）・この PC のイメージ・しくみ
        {"id": "summary", "part": "cfg-container"},
        {"id": "tabs", "layout": "tabs", "children": ["state", "own", "recipe"],
         "props": {"labels": ["状態", "この作業空間だけの設定", "イメージの作り方"]}},

        # 状態（container status・on・off・start・stop・remove）
        {"id": "state", "layout": "column", "children": ["status", "switch", "run", "claude_title", "claude"]},
        {"id": "status", "part": "facts", "props": {
            "items": [
                {"key": "path", "label": "作業空間"}, {"key": "container", "label": "コンテナ"},
                {"key": "state", "label": "状態"}, {"key": "name", "label": "コンテナの名前"},
                {"key": "image", "label": "今のイメージ"}, {"key": "wanted_image", "label": "今の作り方のイメージ"},
                {"key": "outdated", "label": "イメージ"}, {"key": "recipe", "label": "環境の作り方"},
                {"key": "docker_ready", "label": "Docker"}, {"key": "docker_detail", "label": "Docker の状態"},
            ],
            "labels": {
                "container": {"true": "コンテナにする", "false": "コンテナにしない（この PC で動かす）"},
                "state": {"running": "動いている", "exited": "止まっている", "created": "作っただけ", "paused": "一時停止",
                          "none": "まだない", "unknown": "分からない"},
                "outdated": {"true": "古い（次に動かすときに作り直す）", "false": "今の作り方"},
                "docker_ready": {"true": "使える", "false": "まだ使えない"},
            },
        }},
        {"id": "switch", "layout": "row", "children": ["on", "off"]},
        {"id": "on", "part": "button", "props": {"label": "コンテナにする"}},
        {"id": "off", "part": "button", "props": {"label": "コンテナにしない", "hint": "この PC で動かす"}},
        {"id": "run", "layout": "row", "children": ["start", "stop", "remove"]},
        {"id": "start", "part": "button", "props": {"label": "動かす"}},
        {"id": "stop", "part": "button", "props": {"label": "止める"}},
        {"id": "remove", "part": "button", "props": {"label": "コンテナを消す", "hint": "作業空間のファイルはそのまま"}},
        {"id": "claude_title", "part": "note", "props": {"text": "コンテナの中の Claude Code"}},
        {"id": "claude", "part": "facts", "props": {
            "items": [{"key": "setting", "label": "入れる版の設定（空なら、イメージを作るときの最新）"}, {"key": "installed", "label": "入っている版"},
                      {"key": "reason", "label": "補足"}]}},

        # この作業空間だけの設定（container set）
        {"id": "own", "layout": "column", "children": ["own_now", "image_row", "image_default", "deny_row", "deny_clear"]},
        {"id": "own_now", "part": "facts", "props": {
            "items": [{"key": "custom_image", "label": "使うイメージ（空なら型のイメージ）"}, {"key": "deny", "label": "エージェントに使わせないもの"}]}},
        {"id": "image_row", "layout": "row", "children": ["image", "image_set"]},
        {"id": "image", "part": "text-input", "props": {"title": "使うイメージ", "placeholder": "例：ubuntu:24.04"}},
        {"id": "image_set", "part": "button", "props": {"label": "このイメージにする"}},
        {"id": "image_default", "part": "button", "props": {"label": "型のイメージに戻す"}},
        {"id": "deny_row", "layout": "row", "children": ["deny", "deny_set"]},
        {"id": "deny", "part": "list-input", "props": {
            "title": "エージェントに使わせないもの（Claude Code の許可の規則を ; で区切る）", "separator": ";",
            "placeholder": "例：Bash(git push --force:*);WebFetch"}},
        {"id": "deny_set", "part": "button", "props": {"label": "決める"}},
        {"id": "deny_clear", "part": "button", "props": {"label": "使わせないものの設定を消す", "hint": "この PC の設定（agent_deny）だけになる"}},

        # イメージの作り方（container recipe・container image build）
        {"id": "recipe", "layout": "column", "children": ["names", "build", "out", "dockerfile_title", "dockerfile", "layer_title", "layer"]},
        {"id": "names", "part": "facts", "props": {
            "items": [{"key": "module", "label": "モジュール"}, {"key": "environment", "label": "環境のイメージ"},
                      {"key": "image", "label": "コンテナのイメージ"}, {"key": "context", "label": "環境の作り方の場所（空なら型のひな型）"}]}},
        {"id": "build", "part": "button", "props": {"label": "今の作り方でイメージを作る", "hint": "数分かかります"}},
        {"id": "out", "part": "output"},
        {"id": "dockerfile_title", "part": "note", "props": {"text": "環境（.ecobuild/container/Dockerfile。なければ型のひな型）"}},
        {"id": "dockerfile", "part": "text-view"},
        {"id": "layer_title", "part": "note", "props": {"text": "ECOBuild が重ねる層（リポジトリには書きません）"}},
        {"id": "layer", "part": "text-view"},
    ],
    "bindings": [
        # 要約（container recipe・container status・container image list）
        {"read": "container recipe", "args": {"module": {"arg": "module"}}, "to": "summary.recipe"},
        {"read": "container status", "args": {"module": {"arg": "module"}}, "to": "summary.status"},
        {"read": "container image list", "args": {"module": {"arg": "module"}}, "to": "summary.images"},
        # 環境の作り方：Dockerfile のエディター（窓の中に重ねて）・場所を開く（ecobuild open <Dockerfile> --app explorer）・
        # リポジトリに置く（変えるファイルを下見で確かめてから ecobuild module upgrade）
        {"on": "summary.action", "when": {"name": "edit"}, "open": "container-dockerfile", "args": {"module": {"arg": "module"}}, "inside": True},
        {"on": "summary.action", "when": {"name": "reveal"}, "run": "open",
         "args": {"module": {"arg": "module"}, "path": [".ecobuild/container/Dockerfile"], "app": "explorer"}},
        {"on": "summary.action", "when": {"name": "place"}, "open": "mod-upgrade", "args": {"module": {"arg": "module"}}, "inside": True},
        # 状態（container status は1回だけ実行され、2つの部品へ出る）
        {"read": "container status", "args": {"module": {"arg": "module"}}, "to": "status.data"},
        {"read": "container status", "args": {"module": {"arg": "module"}}, "to": "own_now.data"},
        {"read": "agent version status", "args": {"module": {"arg": "module"}}, "to": "claude.data"},
        # 今の状態に合うボタンだけを出す（コンテナにする／しない、動かす／止める、まだないコンテナは消せない）
        {"read": "container status", "args": {"module": {"arg": "module"}}, "into": "container_on", "from": "container"},
        {"read": "container status", "args": {"module": {"arg": "module"}}, "into": "container_state", "from": "state"},
        {"show": "on", "when": {"container_on": False}},
        {"show": "off", "when": {"container_on": True}},
        {"show": "start", "when": {"container_on": True, "container_state": ["exited", "created", "paused", "none", "unknown"]}},
        {"show": "stop", "when": {"container_state": ["running", "paused", "unknown"]}},
        {"show": "remove", "when": {"container_state": ["running", "exited", "created", "paused", "unknown"]}},
        {"on": "on.pressed", "run": "container on", "args": {"module": {"arg": "module"}}},
        {"on": "off.pressed", "run": "container off", "args": {"module": {"arg": "module"}}},
        {"on": "start.pressed", "run": "container start", "args": {"module": {"arg": "module"}}},
        {"on": "stop.pressed", "run": "container stop", "args": {"module": {"arg": "module"}}},
        {"on": "remove.pressed", "run": "container remove", "args": {"module": {"arg": "module"}}},
        # この作業空間だけの設定（ecobuild container set --image <イメージ>・--default-image・--deny <規則>・--no-deny）
        # 今の値を欄に入れておく。書き直すまでは押せない（引数が決まるまで実行しない）
        {"read": "container status", "args": {"module": {"arg": "module"}}, "to": "image.text", "from": "custom_image"},
        {"read": "container status", "args": {"module": {"arg": "module"}}, "to": "deny.items", "from": "deny"},
        {"on": "image.changed", "set": {"image": {"payload": "text"}}},
        {"on": "image_set.pressed", "run": "container set", "require": ["image"],
         "args": {"module": {"arg": "module"}, "image": {"value": "image"}}, "set": {"image": None}},
        {"on": "image_default.pressed", "run": "container set", "args": {"module": {"arg": "module"}, "default_image": True}},
        {"on": "deny.changed", "set": {"deny": {"payload": "text"}}},
        {"on": "deny_set.pressed", "run": "container set", "require": ["deny"],
         "args": {"module": {"arg": "module"}, "deny": {"value": "deny"}}, "set": {"deny": None}},
        {"on": "deny_clear.pressed", "run": "container set", "args": {"module": {"arg": "module"}, "no_deny": True}},
        # イメージの作り方（ecobuild container image build --workspace <作業空間>）
        {"read": "container recipe", "args": {"module": {"arg": "module"}}, "to": "names.data"},
        {"read": "container recipe", "args": {"module": {"arg": "module"}}, "to": "dockerfile.text", "from": "dockerfile"},
        {"read": "container recipe", "args": {"module": {"arg": "module"}}, "to": "layer.text", "from": "layer"},
        {"on": "build.pressed", "run": "container image build",
         "args": {"module": {"arg": "module"}, "workspace": {"arg": "module"}}, "output": "out.lines"},
    ],
}
