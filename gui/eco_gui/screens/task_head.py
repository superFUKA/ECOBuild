"""タスク管理の表示の上の部分：見出しと「更新」「＋ 新しいタスク」、表示のタブと絞り込み（部品 task-bar）。

タスク管理のどの表示（tasks・board・schedule・task-next・task-sprint・task-summary）にも、この画面を置く（つなぎも一緒に入る）。
表示を切り替える・読み直しの要る印を変えると、その表示の画面を、絞り込みを持って開き直す。読み直しの要らない絞り込みは、
共有の値 filter に入れる（絞るのは、表示の部品）。
"""

ARGS = {"module": ".", "view": "tasks", "scope": "all", "filter": {}, "all": False, "ready": False}
# モジュールのフォルダー・今の表示（画面の名前）・この表示に当たる絞り込み（all・assignee・none）・開いたときの絞り込み・
# 上の帯の担当者の候補を読むときの印（閉じたタスクも・着手できるものだけ）

SCREEN = {
    "root": "head",
    "nodes": [
        {"id": "head", "layout": "column", "look": "tk-head", "children": ["top", "bar"]},
        {"id": "top", "layout": "row", "look": "tk-top", "children": ["title", "reload", "new"]},
        {"id": "title", "part": "note", "props": {"text": "タスク管理", "heading": True}},
        {"id": "reload", "part": "button", "props": {"label": "更新"}},
        {"id": "new", "part": "button", "props": {"label": "＋ 新しいタスク", "primary": True}},
        {"id": "bar", "part": "task-bar", "props": {"view": {"arg": "view"}, "scope": {"arg": "scope"}, "start": {"arg": "filter"}}},
    ],
    "bindings": [
        {"read": "task list", "args": {"module": {"arg": "module"}, "all": {"arg": "all"}, "ready": {"arg": "ready"}}, "to": "bar.tasks"},
        {"read": "sprint list", "args": {"module": {"arg": "module"}}, "to": "bar.sprints"},
        {"read": "milestone list", "args": {"module": {"arg": "module"}}, "to": "bar.milestones"},
        {"read": "account show", "args": {"module": {"arg": "module"}}, "to": "bar.me", "from": "login"},
        {"on": "reload.pressed", "refresh": True},
        {"on": "new.pressed", "open": "task-new", "args": {"module": {"arg": "module"}}, "inside": True},
        {"on": "bar.view", "open": {"payload": "id"}, "here": True,
         "args": {"module": {"arg": "module"}, "filter": {"payload": "filter"}, "all": {"payload": "all"}, "ready": {"payload": "ready"}}},
        {"on": "bar.changed", "set": {"filter": {"payload": "filter"}}},
    ],
}
