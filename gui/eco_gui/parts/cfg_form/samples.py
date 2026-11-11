SAMPLES = [
    {"name": "エージェントを追加", "props": {
        "title": "エージェントを追加", "ok": "追加",
        "intro": "このモジュールのエージェント（役）を足します。保存するとリポジトリにコミットし、提出して取り込まれると起動できます。",
        "rows": [{"name": "lead", "title": "進行役", "source": "見本"}, {"name": "worker", "title": "作業役", "source": "見本"}],
        "fields": [
            {"name": "how", "label": "作り方", "type": "radio", "value": "preset", "options": [
                {"value": "preset", "label": "プリセットから作成", "help": "プリセットを写して、名前を付けて足します"},
                {"value": "new", "label": "新規作成", "help": "空の役を作ります（文書・ツールは後で）"}]},
            {"name": "from_preset", "label": "元にするプリセット", "type": "select", "show_if": {"how": "preset"},
             "options_from": {"value": "name", "label": "title", "note": "source"}},
            {"name": "name", "label": "名前（英小文字・数字・-・_）", "placeholder": "例：reviewer", "help": "プリセットから作るときは、空ならプリセットと同じ名前",
             "empty_uses": "from_preset", "required": True},
            {"name": "title", "label": "表示名", "placeholder": "例：レビュー役", "show_if": {"how": "new"}},
            {"name": "human_start", "label": "人が手で起動できる（作業空間の「エージェント」の ＋ に出る）", "type": "checkbox", "value": True},
        ]}},
    {"name": "節・読んだ値・数", "props": {
        "title": "ビルド設定「release」を編集", "ok": "保存",
        "values": {"configuration": "Release", "jobs": 8, "cpp": {"standard": "20"}, "definitions": ["A=1", "B"]},
        "fields": [
            {"name": "configuration", "label": "構成", "type": "select", "options": [{"value": "Debug", "label": "Debug"}, {"value": "Release", "label": "Release"}]},
            {"name": "jobs", "label": "並列数（0 は自動）", "type": "number"},
            {"type": "section", "label": "C++・コンパイラ", "collapsed": True},
            {"name": "standard", "label": "C++ 規格", "value_from": "cpp.standard"},
            {"name": "definitions", "label": "マクロ定義", "type": "textarea", "join": "\n"},
            {"type": "section", "label": "テスト・依存先", "collapsed": False},
            {"name": "tests", "label": "テストをビルドする", "type": "checkbox"},
        ]}},
    {"name": "戻せない操作", "props": {"title": "消す", "ok": "消す", "danger": True, "fields": [{"type": "note", "label": "本当に消しますか。"}]}},
    {"name": "誤り", "props": {"title": "エージェントを追加", "fields": [{"name": "name", "label": "名前"}], "error": "一覧を読めません"}},
]
