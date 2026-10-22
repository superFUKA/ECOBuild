"""シェルのコマンドの関所（エージェントの PreToolUse フック）。何を通すかは使う側が Policy で決める。

通すのは、許したプログラム（policy.programs）と読むだけのコマンドだけ。ファイルへの書き出し（>）・コマンドの埋め込み（$(…)・`）は止める。
出力を捨てる・まとめるだけの書き方（2>/dev/null・2>&1 等）と、for・if・while の組み立ては、中のコマンドを調べて通す。
許したプログラムの引数は policy.classify で重さ（READ・CHANGE・CONFIRM・HUMAN）に分ける：
- CONFIRM（消す・取り返しがつかない・ほかの人に届く）は、エージェントが直前の返答でそのコマンドを示して聞き、
  ユーザーが次の発言で「はい」と答えたときだけ通す（会話の記録から読む）。
- HUMAN（人が画面で答える操作・管理者の権限が要る操作）は通さない。
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

READ = "read"           # 見るだけ
CHANGE = "change"       # 変える（戻せる）
CONFIRM = "confirm"     # 消す・取り返しがつかない・ほかの人に届く：ユーザーの「はい」が要る
REQUESTED = "requested" # ユーザーが直前の発言で頼んだときだけ（ほかのエージェントへ文字を送る等：「送って」「伝えて」）
HUMAN = "human"         # 人がする操作：エージェントは使わない

READ_ONLY = frozenset({
    "ls", "dir", "cat", "type", "head", "tail", "grep", "rg", "findstr", "wc", "pwd", "which", "where", "echo",
    "get-childitem", "gci", "get-content", "gc", "select-string", "sls", "test-path", "get-location", "get-command",
    "select-object", "where-object", "sort-object", "measure-object", "format-table", "format-list",
})

_YES = re.compile(r"はい|うん|ええ|お願い|おねがい|よろしく|どうぞ|いいよ|いいです|いいね|大丈夫|だいじょうぶ|構わ|かまわ|"
                  r"実行|やって|進めて|続けて|ok|okay|オッケー|オーケー|yes|sure", re.IGNORECASE)
_NO = re.compile(r"いいえ|いや|やめ|止め|待って|まって|ダメ|だめ|駄目|中止|キャンセル|しないで|しなくて|違う|ちがう|"
                 r"\bno\b|\bstop\b|\bcancel\b", re.IGNORECASE)
_SEPARATORS = re.compile(r"\|\||&&|[|;&\n]")
# ファイルに書かない書き出し：捨てる（/dev/null・nul・$null）か、エラーを出力にまとめる（2>&1）
_DISCARD = re.compile(r"(?<![\w>&])[12]?>\s*(?:/dev/null|nul|\$null)(?![\w/.])|(?<![\w>&])2>&1(?!\w)", re.IGNORECASE)
_KEYWORDS = frozenset({"do", "then", "else", "elif", "if", "while", "until", "!", "{"})   # 後ろにコマンドが続く
_ENDS = frozenset({"done", "fi", "}"})
_VARIABLE = re.compile(r"\$(?:\{(\w+)\}|(\w+))")
# 文字を送ることをユーザーが頼んだと分かる言葉（音声入力なので、言い回しは広めに）
_ASKED = re.compile(r"送|伝え|言って|頼ん|入力|打って|打ち込|エンター|enter|押して", re.IGNORECASE)


@dataclass(frozen=True)
class Policy:
    """programs：許すプログラムの名前（拡張子なし・小文字）。classify(引数) → (重さ, 確認のときに示すべき言葉)。"""
    programs: frozenset[str]
    classify: Callable[[list[str]], tuple[str, str]]
    read_only: frozenset[str] = READ_ONLY
    role: str = "このエージェント"
    refusals: dict[str, str] = field(default_factory=dict)      # 重さ → 止めたときに足す文（HUMAN 等）
    classifiers: dict[str, Callable[[list[str]], tuple[str, str]]] = field(default_factory=dict)   # プログラムごとの classify


@dataclass(frozen=True)
class Exchange:
    """会話の最後のやりとり：エージェントの直前の返答と、それに続くユーザーの発言。"""
    reply: str = ""
    prompt: str = ""


def check(command: str, policy: Policy, exchange: Exchange | None = None) -> str | None:
    """通してよければ None、止めるならその理由（エージェントにそのまま伝える文）。"""
    exchange = exchange or Exchange()
    quoted: list[str] = []

    def keep(match: re.Match) -> str:
        quoted.append(match.group(0))
        return f"\0{len(quoted) - 1}\0"

    bare = re.sub(r'"(?:\\.|[^"\\])*"|\'[^\']*\'', keep, command)      # 引用符の中（コミットの文など）は調べない
    bare = _DISCARD.sub(" ", bare)
    if re.search(r"[>`]|\$\(|<\(", bare):
        return "ファイルへの書き出し（>）やコマンドの埋め込み（$(…)・`）は使えません。"
    loops: dict[str, list[str]] = {}    # for の変数 → 値
    for part in _SEPARATORS.split(bare):
        part = re.sub(r"\0(\d+)\0", lambda m: quoted[int(m.group(1))], part).strip()
        if not part:
            continue
        try:
            words = shlex.split(part, posix=True)
        except ValueError:
            return "コマンドを読み取れませんでした（引用符が閉じていません）。"
        while words and words[0] in _KEYWORDS:
            words = words[1:]
        if not words or words[0] in _ENDS:
            continue
        if words[0] == "for":
            if len(words) < 3 or words[2] != "in" or not re.fullmatch(r"\w+", words[1]):
                return "for は「for <変数> in <値>…; do <コマンド>; done」の形で書いてください。"
            loops[words[1]] = words[3:]
            continue
        name = re.sub(r"\.(exe|cmd|bat|ps1)$", "", Path(words[0].replace("\\", "/")).name, flags=re.IGNORECASE).lower()
        if name in policy.programs:
            for args in _expanded(words[1:], loops):    # for の変数は、値を1つずつ入れて調べる
                problem = _program(args, policy, exchange, policy.classifiers.get(name, policy.classify))
                if problem:
                    return problem
        elif name not in policy.read_only:
            names = "・".join(sorted(policy.programs))
            return (f"「{words[0]}」は使えません。{policy.role}が使えるのは {names} と、読むだけのコマンド"
                    "（ls・cat・grep など）です。ファイルの作成・編集・移動・削除はしません。")
    return None


def _expanded(args: list[str], loops: dict[str, list[str]]) -> list[list[str]]:
    """args の for の変数に、値を1つずつ入れたもの（for の変数がなければ args だけ）。"""
    used = {name for a in args for name in _names(a)} & loops.keys()
    if not used:
        return [args]
    found = []
    for name in sorted(used):
        for value in loops[name] or [""]:
            found.append([w for a in args for w in
                          (_VARIABLE.sub(lambda m: value if (m.group(1) or m.group(2)) == name else m.group(0), a).split()
                           if name in _names(a) else [a])])
    return found


def _names(text: str) -> set[str]:
    return {m.group(1) or m.group(2) for m in _VARIABLE.finditer(text)}


def _program(args: list[str], policy: Policy, exchange: Exchange, classify=None) -> str | None:
    weight, words = (classify or policy.classify)(args)
    if weight == HUMAN:
        return policy.refusals.get(HUMAN, "これは人が行う操作です。ユーザーに実行してもらうよう伝えてください。")
    if weight == REQUESTED and not _ASKED.search(exchange.prompt or ""):
        return (f"これ（{words}）は、ユーザーが直前の発言で「〇番に〜と送って」のように頼んだときだけ使えます。"
                "依頼文を自分で作って送らないでください（受け取ったエージェントは、それを人の指示として実行します）。"
                "「〜で始めて」「〜を立ち上げて」は、ほとんどがエージェントを開くことです。分からなければ短く聞き返してください。")
    if weight == CONFIRM and not confirmed(words, exchange):
        return (f"これは取り返しのつかない操作か、ほかの人に届く操作です（{words}）。実行する前に、"
                f"実行するコマンドをそのまま示してユーザーに聞き、「はい」（お願い・OK・y 等）と答えてもらってから実行してください。"
                "聞かずに実行したり、別の方法で同じことをしたりしないでください。")
    return None


def confirmed(words: str, exchange: Exchange) -> bool:
    """エージェントが直前の返答で words（コマンドの名前）を示し、ユーザーがそれに「はい」と答えたか。"""
    reply = " ".join(exchange.reply.split())
    prompt = exchange.prompt.strip()
    yes = bool(_YES.search(prompt)) or prompt.lower().rstrip(".。") == "y"
    return bool(words) and words in reply and yes and not _NO.search(prompt)


def last_exchange(transcript: Path | str | None) -> Exchange:
    """会話の記録（Claude Code の JSONL）から、ユーザーの最後の発言と、その直前のエージェントの返答の文を取り出す。
    ツールの結果・システムの差し込み（< で始まる文）は発言に数えない。読めなければ空。"""
    if not transcript:
        return Exchange()
    try:
        lines = Path(transcript).read_text(encoding="utf-8").splitlines()
    except OSError:
        return Exchange()
    prompt = None
    replies: list[str] = []
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        kind = entry.get("type")
        content = (entry.get("message") or {}).get("content")
        if kind == "user" and not entry.get("isMeta"):
            text = _user_text(content)
            if text is None:
                continue
            if prompt is None:
                prompt = text
            else:
                break       # その前の発言まで来た：返答はここまで
        elif kind == "assistant" and prompt is not None:
            replies.append(_assistant_text(content))
    return Exchange("\n".join(reversed([r for r in replies if r])), prompt or "")


def _user_text(content) -> str | None:
    if isinstance(content, str):
        text = content
    elif isinstance(content, list) and not any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
        text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    else:
        return None
    return text if text.strip() and not text.lstrip().startswith("<") else None


def _assistant_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def hook(data: str, policy: Policy) -> tuple[int, str]:
    """フックの入力（JSON）を調べる。(終了コード, stderr に出す文)。止めるときは 2（文がエージェントに伝わる）。"""
    try:
        event = json.loads(data or "{}")
    except ValueError:
        return 0, ""
    command = (event.get("tool_input") or {}).get("command") or ""
    problem = check(command, policy, last_exchange(event.get("transcript_path")))
    return (2, problem) if problem else (0, "")
