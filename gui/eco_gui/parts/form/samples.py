SAMPLES = [
    {"name": "欄の種類（必須・横に並べる・節・複数入れる・いくつか選ぶ）", "props": {
        "title": "新しいタスク", "ok": "作成",
        "fields": [
            {"name": "title", "label": "題名", "required": True},
            {"name": "body", "label": "本文", "type": "textarea", "rows": 3, "placeholder": "背景・完了の条件など（任意）"},
            {"name": "stage", "label": "段階", "type": "radio", "inline": True, "value": "todo", "hide_if": {"start": True}, "options": [
                {"value": "todo", "label": "未着手"}, {"value": "planned", "label": "計画中", "help": "まだ着手しない（内容・時期を詰めている）"}]},
            {"name": "assignee", "label": "担当者", "type": "checks", "join": ",", "value": "octocat",
             "options": [{"value": "octocat", "label": "octocat（自分）"}, {"value": "hubot", "label": "hubot"}, {"value": "mona", "label": "mona"}]},
            {"type": "section", "label": "計画"},
            {"name": "priority", "label": "優先度", "type": "select", "row": "plan", "none_label": "なし",
             "options": [{"value": "High", "label": "High"}, {"value": "Middle", "label": "Middle"}, {"value": "Low", "label": "Low"}]},
            {"name": "estimate", "label": "見積もり", "type": "number", "row": "plan", "step": 0.5},
            {"name": "due", "label": "期限", "type": "date", "row": "plan"},
            {"type": "section", "label": "分類・つながり", "note": "ラベル・先に終わるべきタスク", "collapsed": True},
            {"name": "label", "label": "ラベル", "multiple": True, "join": ",", "value": ["bug", "ui"], "placeholder": "なければ作ります"},
            {"name": "blocked_by", "label": "先に終わるべきタスク", "placeholder": "番号（カンマ区切り）"},
            {"type": "section", "end": True},
            {"name": "start", "label": "作成したら、作業空間を作って作業を開始する", "type": "checkbox", "strong": True},
            {"name": "name", "label": "タスクブランチの名前", "required": True, "show_if": {"start": True},
             "help": "task/〈番号〉-〈名前〉のブランチになります（既定は題名）。"},
        ]}},
    {"name": "何が起きるかの表（欄の値で変わる）・読んだ値", "props": {
        "title": "取り込む：#{number}", "ok": "取り込む",
        "values": {"number": 12, "base": "main", "pull_request": {"state": "open", "partial": True}},
        "outcome": [
            {"label": "取り込み", "text": "CI を待って、提出を作成元（{base}）へ取り込みます"},
            {"label": "タスク", "text": "閉じて、タスクブランチを片付けます", "show_if": {"complete": True}},
            {"label": "タスク", "text": "閉じずに続けます（タスクブランチを作成元の最新から作り直します）", "show_if": {"complete": False}}],
        "fields": [
            {"name": "subject", "label": "取り込むコミットの件名（空ならタスクの題名）"},
            {"name": "ignore_checks", "label": "CIが失敗していても取り込む", "type": "checkbox"},
            {"name": "complete", "label": "タスクを完了する", "type": "checkbox", "value_from": "pull_request.partial", "off_value": True, "inverse": "partial"},
        ]}},
    {"name": "読んだ一覧から選ぶ・条件で出る欄・空なら代わりの欄", "props": {
        "title": "エージェントを追加", "ok": "追加",
        "intro": "このモジュールのエージェント（役）を足します。保存するとリポジトリにコミットし、提出して取り込まれると起動できます。",
        "rows": [{"name": "lead", "title": "進行役", "source": "sample"}, {"name": "worker", "title": "作業役", "source": "preset"}],
        "fields": [
            {"name": "how", "label": "作り方", "type": "radio", "value": "preset", "options": [
                {"value": "preset", "label": "プリセットから作成", "help": "プリセットを写して、名前を付けて足します"},
                {"value": "new", "label": "新規作成", "help": "空の役を作ります（文書・ツールは後で）"}]},
            {"name": "from_preset", "label": "元にするプリセット", "type": "select", "show_if": {"how": "preset"},
             "options_from": {"value": "name", "label": "title", "note": ["name", "source"], "note_labels": {"sample": "見本", "preset": "このPCのプリセット"}}},
            {"name": "name", "label": "名前（英小文字・数字・-・_）", "placeholder": "例：reviewer", "help": "プリセットから作るときは、空ならプリセットと同じ名前",
             "empty_uses": "from_preset", "required": True},
            {"name": "title", "label": "表示名", "placeholder": "例：レビュー役", "show_if": {"how": "new"}},
            {"name": "human_start", "label": "人が手で起動できる（作業空間の「エージェント」の ＋ に出る）", "type": "checkbox", "value": True},
        ]}},
    {"name": "読んだ今の値・畳める節・数", "props": {
        "title": "ビルド設定", "subject": "release", "ok": "保存", "at": ["release"],
        "values": {"release": {"name": "release", "configuration": "Release", "parallel": 8, "options": {"cpp_standard": "20", "fetch_git": False}}},
        "fields": [
            {"name": "name", "label": "名前", "required": True},
            {"name": "configuration", "label": "構成", "type": "select", "options": [{"value": "Debug", "label": "Debug"}, {"value": "Release", "label": "Release"}]},
            {"name": "parallel", "label": "並列ビルドの数", "type": "number", "min": 1, "value": 4},
            {"type": "section", "label": "C++・コンパイラ（空なら既定）", "collapsed": True},
            {"name": "cpp_standard", "label": "C++の規格", "value_from": "options.cpp_standard"},
            {"type": "section", "label": "テスト・依存先（空なら既定）", "collapsed": False},
            {"name": "no_fetch", "label": "足りない依存先を、ビルドの前に自動でcloneしない", "type": "checkbox", "value_from": "options.fetch_git", "on_value": False},
        ]}},
    {"name": "戻せない操作・警告の帯", "props": {
        "title": "作業を捨てる：#{issue}", "ok": "作業を捨てる", "danger": True, "vars": {"issue": 12, "conflicts": ["src/app.py", "README.md"]},
        "intro": "作業を取り込まずに捨てます。提出を閉じ、タスクブランチをこのPCとGitHubから消して、その作業空間も消します。捨てた作業は戻せません。",
        "fields": [
            {"type": "note", "tone": "bad", "label": "作成元と衝突しています。最新を取り込んで直してから提出してください。", "list_from": "conflicts"},
            {"name": "close", "label": "タスクも削除する", "type": "checkbox"}]}},
    {"name": "実行できなかった（理由は窓の中に。値は残る）", "props": {
        "title": "ブランチを作成", "ok": "作成", "initial": {"name": "main"}, "problem": "ブランチ main は既にあります。",
        "fields": [{"name": "name", "label": "ブランチ名", "required": True}]}},
    {"name": "読み込み中", "props": {"title": "CIを手動で実行", "ok": "実行", "loading": True,
                                "fields": [{"name": "branch", "label": "ブランチ", "type": "select", "options_from": {"source": "rows"}}]}},
    {"name": "誤り", "props": {"title": "CIを手動で実行", "ok": "実行", "error": "一覧を読めません",
                             "fields": [{"name": "branch", "label": "ブランチ", "type": "select", "options_from": {"source": "rows"}}]}},
]
