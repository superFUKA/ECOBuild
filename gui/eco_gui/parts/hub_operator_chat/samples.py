SAMPLES = [
    {"name": "会話の前（紹介）", "props": {
        "conversation": {"messages": [], "state": "idle"},
        "intro": "AI はコードを書かず、ecobuild のコマンドで操作します。消す・取り返しのつかない操作は、実行する前に確認します。"}},
    {"name": "会話（待機中）", "props": {"conversation": {"state": "idle", "messages": [
        {"role": "user", "text": "ECOSTL のタスクを見せて", "at": 1},
        {"role": "agent", "ok": True, "at": 2, "text": "ECOSTL のタスク管理を開きました。\n開いているタスクは **3 件** です（`task list`）。",
         "actions": [{"command": "ecobuild -C C:/ECO/ECOSTL task list", "ok": True},
                     {"command": "ecobuild gui open --module C:/ECO/ECOSTL --page tasks", "ok": True}]},
        {"role": "user", "text": "12番を始めて", "at": 3},
        {"role": "agent", "ok": True, "at": 4, "text": "タスクを始める操作は、タスク管理の「始める」で行えます（開きました）。",
         "actions": [{"command": "ecobuild -C C:/ECO/ECOSTL task start 12", "ok": False},
                     {"command": "ecobuild gui open --module C:/ECO/ECOSTL --page tasks --task 12", "ok": True}]}]}}},
    {"name": "送った後（考え中・実行中のコマンド）", "props": {
        "conversation": {"state": "idle", "messages": [
            {"role": "user", "text": "ECOSTL のタスクを見せて", "at": 1},
            {"role": "agent", "ok": True, "at": 2, "text": "ECOSTL のタスク管理を開きました。", "actions": []}]},
        "asked": "12番はどうなってる？", "doing": ["ecobuild -C C:/ECO/ECOSTL task show 12"]}},
    {"name": "失敗した返答", "props": {"conversation": {"state": "idle", "messages": [
        {"role": "user", "text": "一覧を見せて", "at": 1},
        {"role": "agent", "ok": False, "at": 2, "actions": [],
         "text": "エージェント claude が見つかりません。\nclaude をインストールし、PATH から実行できるようにしてください。"}]}}},
    {"name": "送れなかった", "props": {
        "conversation": {"state": "idle", "messages": [{"role": "user", "text": "一覧を見せて", "at": 1},
                                                       {"role": "agent", "ok": True, "at": 2, "text": "3 件あります。", "actions": []}]},
        "failed": "ecobuild gui というコマンドはありません。"}},
    {"name": "起動中（画面の最後の数行）", "props": {"conversation": {
        "messages": [], "state": "starting", "starting_for": 14,
        "screen": "Welcome to Claude Code\n> Do you trust the files in this folder?\n  1. Yes, proceed"}}},
    {"name": "裏で実行中", "props": {"conversation": {
        "messages": [{"role": "user", "text": "ECOSTL のタスクを見せて", "at": 1}], "state": "waiting", "doing": "ecobuild workspace list", "queued": 1}}},
    {"name": "選択肢を出しています", "props": {"conversation": {
        "messages": [{"role": "user", "text": "タスクを見せて", "at": 1}], "state": "choice",
        "choice": {"question": "どのモジュールですか？", "choice": "1. ECOSTL"}}}},
    {"name": "終わりました", "props": {"conversation": {"state": "exited", "messages": [
        {"role": "user", "text": "ありがとう", "at": 1}, {"role": "agent", "ok": True, "at": 2, "text": "どういたしまして。", "actions": []}]}}},
    {"name": "読み込み中", "props": {"loading": True}},
    {"name": "読めなかった", "props": {"error": "ecobuild gui conversation を実行できませんでした。"}},
]
