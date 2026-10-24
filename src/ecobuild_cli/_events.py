"""CLIの標準エラー：経過・知らせ・注意・誤りと、動かしたツール・プログラムの出力を出す口（どこからもここを通す）。

標準出力はコマンドの結果だけ（--json なら JSON が1つ）。それ以外はすべてここから標準エラーへ出す。

- 人向け：今までどおりの文字。経過・注意はそのまま、知らせは「お知らせ：」、誤りは「エラー：」（詳細・ヒントの行も）。
  ツール・プログラムの出力は印を付けずにそのまま（プログラムの標準出力は標準出力へ、標準エラーは標準エラーへ）。
- --json：1行1件の JSON のイベント（JSON Lines。go test -json・terraform -json・cargo --message-format=json と同じ
  考え方：流れの中の1件ずつを、種類の付いた JSON で）。キーと意味は EVENT_KEYS（ecobuild --help --json の events）。
  結果は今までどおり標準出力の JSON だけで分かる（イベントは途中の様子を見るためのもの。知らせ・誤りは結果にも入る）。

イベントには run の ID を付けない（結果の JSON の log.run にある。コンテナの中の ecobuild のイベントは、そのまま通る）。
"""

from __future__ import annotations

import datetime
import json
import sys
import threading

KINDS = ("progress", "notice", "warning", "error", "output")
STREAMS = ("stdout", "stderr")
SOURCES = ("program", "tool")

# --json の標準エラーのイベントのキー（ecobuild --help --json の events に出す。エージェント・GUI が読む）
EVENT_KEYS = {
    "kind": "イベントの種類。progress（経過：今していること）・notice（知らせ：結果の notices と同じ）・"
            "warning（注意：続けるが確かめてほしいこと）・error（誤り：結果の error と同じ。終わる直前に1つ）・"
            "output（ビルド・テスト・実行で動かしたツール・プログラムの出力）",
    "text": "文。output では、ツール・プログラムが書いたとおりの文字（ふつうは1行で、終わりの改行 \\n も含む。"
            "入力の催促等の行の途中までなら改行なし。stream ごとにつなげると出力の全部になる）",
    "time": "出した時刻（ISO 8601、UTC、ミリ秒まで。ログの time と同じ）",
    "stream": "output だけ：ツール・プログラムのどちらの出力か（stdout・stderr）",
    "source": "output だけ：program（ecobuild run で実行しているプログラム）・tool（ビルド・テストのツール：CMake・"
              "コンパイラー・CTest・テストのプログラム・pip 等）",
    "code": "error だけ：誤りの種類（結果の error.code と同じ）",
}
RAW_LINES = ("JSON として読めない行が混ざることがある（ECOBuild が標準エラーを受け継がせた子プロセス〔コンテナの docker 等〕"
             "が直に書いたもの）。そのときは kind output・stream stderr・source tool の text とみなす。")

_lock = threading.Lock()


def schema() -> dict:
    """イベントの形（ecobuild --help --json の events）。"""
    return {"format": "JSON Lines（標準エラーの1行1件。--json のとき）", "kinds": list(KINDS), "keys": EVENT_KEYS,
            "streams": list(STREAMS), "sources": list(SOURCES), "raw_lines": RAW_LINES}


def emit(kind: str, text: str, *, json_output: bool, human: str | None = None, **fields) -> None:
    """イベントを1つ出す。human：人向けの表示（省けば text。経過・注意はそのまま、知らせ・誤りは頭の言葉を付ける）。
    fields：output の stream・source、error の code。いくつかのスレッド（プログラムの stdout・stderr）から呼んでよい。"""
    if not text and kind != "output":
        return
    if json_output:
        event = {"kind": kind, "text": text, "time": _now(), **{k: v for k, v in fields.items() if v is not None}}
        _write(sys.stderr, json.dumps(event, ensure_ascii=False) + "\n")
    elif kind == "output":
        _write(sys.stdout if fields.get("stream") == "stdout" else sys.stderr, text)
    else:
        shown = human if human is not None else {"notice": f"お知らせ：{text}", "error": f"エラー：{text}"}.get(kind, text)
        _write(sys.stderr, shown + "\n")


def progress(text: str, json_output: bool) -> None:
    """経過（今していること）。頭が「注意：」の文は注意（warning）にする（本体の経過の口から来るもの）。"""
    emit("warning" if text.startswith("注意：") else "progress", text, json_output=json_output)


def output(text: str, json_output: bool, *, stream: str = "stdout", source: str = "program") -> None:
    """ツール・プログラムの出力（書いたとおりの文字。--json では1行ずつのイベントに分ける）。"""
    text = text.replace("\r\n", "\n")
    if not text:
        return
    if not json_output:
        emit("output", text, json_output=False, stream=stream, source=source)
        return
    for piece in text.splitlines(keepends=True):
        emit("output", piece, json_output=True, stream=stream, source=source)


def _write(stream, text: str) -> None:
    with _lock:
        stream.write(text)
        stream.flush()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


# 読む側（ほかの ecobuild の標準エラーを読むところ：係・GUI と同じ決まり） --------------------------------------------

def parse(line: str) -> dict | None:
    """標準エラーの1行のイベント。JSON のイベントでない行は None（RAW_LINES：ツールの標準エラーの出力とみなす）。"""
    stripped = line.strip()
    if not stripped.startswith("{"):
        return None
    try:
        event = json.loads(stripped)
    except ValueError:
        return None
    return event if isinstance(event, dict) and event.get("kind") in KINDS and isinstance(event.get("text"), str) \
        else None


def messages(text: str) -> str:
    """標準エラーの全部から、ツール・プログラムの出力のイベントを除いた文（ECOBuild の文と、JSON でない行）。失敗の説明に。"""
    found = []
    for line in text.splitlines():
        event = parse(line)
        if event is None and line.strip():
            found.append(line.rstrip() + "\n")
        elif event is not None and event["kind"] != "output":
            found.append(event["text"] + "\n")
    return "".join(found)
