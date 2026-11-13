"""モジュールの窓の「作業空間」の上の部分（frame-workspaces・frame-workspace に置く）：既定のブランチにいないときの帯と、作業空間のタブ。

タブを選ぶと、同じ窓で、その作業空間を出した画面（frame-workspace）に切り替わる。出すタブがなくなれば、案内の画面（frame-workspaces）へ。
閉じたタブ（closed）は画面の引数でも運ぶ（タブの部品も、窓を開いているあいだ覚えている：ほかのページから戻っても閉じたまま）。"""

ARGS = {"module": ".", "space": "", "closed": []}  # モジュールのフォルダー・今出している作業空間・閉じたタブ

SCREEN = {
    "root": "bar",
    "nodes": [
        {"id": "bar", "layout": "column", "look": "frame-bar", "children": ["band", "tabs"]},
        {"id": "band", "part": "frame-band", "props": {"module": {"arg": "module"}}},
        {"id": "tabs", "part": "frame-tabs", "props": {"current": {"arg": "space"}, "closed": {"arg": "closed"}, "module": {"arg": "module"}}},
    ],
    "bindings": [
        {"read": "workspace list", "to": "band.modules", "from": "modules"},
        # 作業空間のタブ：見えているあいだ 20 秒ごとに読み直す（ほかの窓・端末・エージェントが作った・消した作業空間。前の GUI と同じ）。
        # 手元の git だけを読む。GitHub に聞く task list は、この間隔では読まない
        {"read": "module show", "args": {"module": {"arg": "module"}}, "to": "tabs.workspaces", "from": "workspaces", "every": 20},
        {"read": "task list", "args": {"module": {"arg": "module"}}, "to": "tabs.tasks"},
        # Visual Studio の版ごとに、開けるか（入っていない版は、メニューで灰色と理由）
        {"can": "open", "args": {"module": {"arg": "module"}, "app": "vs", "vs_version": "2026"}, "to": "tabs.vs2026"},
        {"can": "open", "args": {"module": {"arg": "module"}, "app": "vs", "vs_version": "2022"}, "to": "tabs.vs2022"},
        # 開く版：作業空間の道具の帯で選んだもの（中に置いた作業空間の画面と、同じ窓の共有の値）
        {"value": "vs_version", "to": "tabs.vs_version"},
        # タブを選ぶ・閉じる：同じ窓で切り替える
        {"on": "tabs.selected", "open": "frame-workspace",
         "args": {"module": {"arg": "module"}, "space": {"payload": "path"}, "closed": {"payload": "closed"}}, "here": True},
        {"on": "tabs.emptied", "open": "frame-workspaces", "args": {"module": {"arg": "module"}, "closed": {"payload": "closed"}}, "here": True},
        # 右クリックのメニュー・一覧（この PC の道具で開く＝ecobuild open、作業空間を削除＝ecobuild workspace close）
        {"on": "tabs.action", "when": {"name": "explorer"}, "run": "open", "args": {"module": {"payload": "path"}, "app": "explorer"}},
        # Visual Studio：ソリューションで開く（ecobuild open --app vs --solution）。まだなければ「ビルドしてから開きますか？」
        {"on": "tabs.action", "when": {"name": "vs"}, "run": "open",
         "args": {"module": {"payload": "path"}, "app": "vs", "vs_version": {"payload": "version"}, "solution": True},
         "notify": "Visual Studio[ {version}] で開きます[：{name}]",
         "instead": {"when": {"code": "no_solution"}, "open": "frame-vs-build", "inside": True,
                     "args": {"module": {"payload": "path"}, "version": {"payload": "version"}}}},
        {"on": "tabs.action", "when": {"name": "reload"}, "refresh": True},
        {"on": "tabs.action", "when": {"name": "remove"}, "run": "workspace close", "args": {"module": {"arg": "module"}, "at": {"payload": "path"}},
         "notify": "作業空間を削除しました。"},
        {"on": "tabs.action", "when": {"name": ["task", "tasks"]}, "open": "tasks", "args": {"module": {"arg": "module"}}, "here": True},
    ],
}
