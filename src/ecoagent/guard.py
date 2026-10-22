"""シェルのコマンドの関所（エージェントの PreToolUse フック）。何を通すか・止めるかは使う側が決める。

2つの向きがある：
- Policy（許すものの列挙）：許したプログラムと読むだけのコマンドだけを通す（下の check・hook）。
- Denied（ダメなものの列挙）：止めるものだけを書き、ほかはすべて通す（check_denied・hook_denied）。隔離した場所で
  確認なしに動くエージェントが、決まった道（ツール）を外れないように使う。

Policy：通すのは、許したプログラム（policy.programs）と読むだけのコマンドだけ。ファイルへの書き出し（>）・コマンドの埋め込み（$(…)・`）は止める。
出力を捨てる・まとめるだけの書き方（2>/dev/null・2>&1 等）と、for・if・while の組み立ては、中のコマンドを調べて通す。
許したプログラムの引数は policy.classify で重さ（READ・CHANGE・CONFIRM・HUMAN）に分ける：
- CONFIRM（消す・取り返しがつかない・ほかの人に届く）は、エージェントが直前の返答でそのコマンドを示して聞き、
  ユーザーが次の発言で「はい」と答えたときだけ通す（会話の記録から読む）。
- HUMAN（人が画面で答える操作・管理者の権限が要る操作）は通さない。
"""

from __future__ import annotations

import itertools
import json
import math
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
            expanded = _expanded(words[1:], loops)     # for の変数は、値を入れて調べる
            if expanded is None:
                return "for の値の組み合わせが多すぎます。分けて実行してください。"
            for args in expanded:
                problem = _program(args, policy, exchange, policy.classify)
                if problem:
                    return problem
        elif name not in policy.read_only:
            names = "・".join(sorted(policy.programs))
            return (f"「{words[0]}」は使えません。{policy.role}が使えるのは {names} と、読むだけのコマンド"
                    "（ls・cat・grep など）です。ファイルの作成・編集・移動・削除はしません。")
    return None


def _expanded(args: list[str], loops: dict[str, list[str]]) -> list[list[str]] | None:
    """args の for の変数に値を入れたもの：変数の値の組み合わせをすべて（for の変数がなければ args だけ。多すぎれば None）。"""
    used = sorted({name for a in args for name in _names(a)} & loops.keys())
    if not used:
        return [args]
    if math.prod(max(len(loops[name]), 1) for name in used) > 200:
        return None
    found = []
    for values in itertools.product(*(loops[name] or [""] for name in used)):
        chosen = dict(zip(used, values))
        found.append([w for a in args for w in
                      (_VARIABLE.sub(lambda m: chosen.get(m.group(1) or m.group(2), m.group(0)), a).split()
                       if chosen.keys() & _names(a) else [a])])
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



# ---- ダメなものの列挙 -------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Denied:
    """逆向きの関所：止めるものだけを列挙し、ほかはすべて通す。
    programs：まるごと止めるプログラムの名前（拡張子なし・小文字）→ 止めたわけ。
    commands：引数で決めるプログラム → 関数（引数 → 止めるわけ。通すなら None）。"""
    programs: dict[str, str] = field(default_factory=dict)
    commands: dict[str, Callable[[list[str]], str | None]] = field(default_factory=dict)


SHELLS = frozenset({"sh", "bash", "dash", "zsh", "ksh"})          # -c の文字列の中も調べる
# 後ろのコマンドを動かすだけのもの（その後ろを調べる）。値を1つ取るオプション
_WRAPPERS = {"env": (), "command": (), "builtin": (), "exec": (), "nohup": (), "time": (), "sudo": ("-u", "-g"),
             "nice": ("-n",), "timeout": ("-s", "-k"), "xargs": ("-n", "-I", "-L", "-P", "-d", "-a", "-s", "-E"),
             "stdbuf": ("-i", "-o", "-e"), "watch": ("-n",), "doas": ("-u",)}
_ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")


def check_denied(command: str, denied: Denied) -> str | None:
    """通してよければ None、止めるならその理由。コマンドの埋め込み（$(…)・`…`。" の中も）と sh -c・eval の文字列の
    中も調べる。読み取れないもの（引用符が閉じていない等）は止める（ダメなものを見落とさないように）。"""
    try:
        segments = _segments(command)
    except ValueError:
        return "コマンドを読み取れませんでした（引用符が閉じていません）。"
    for words in segments:
        problem = _denied_words(words, denied, depth=0)
        if problem:
            return problem
    return None


def _denied_words(words: list[str], denied: Denied, depth: int) -> str | None:
    words = _command_words(words)
    if not words:
        return None
    name = re.sub(r"\.(exe|cmd|bat|ps1|sh)$", "", Path(words[0].replace("\\", "/")).name, flags=re.IGNORECASE).lower()
    args = words[1:]
    if name in denied.programs:
        return denied.programs[name]
    if name in denied.commands:
        problem = denied.commands[name](args)
        if problem:
            return problem
    inner = None
    if name in SHELLS and "-c" in args[:-1]:
        inner = args[args.index("-c") + 1]
    elif name == "eval":
        inner = " ".join(args)
    if inner is not None:
        if depth > 5:
            return "入れ子が深すぎるコマンドです。分けて実行してください。"
        try:
            segments = _segments(inner)
        except ValueError:
            return "コマンドを読み取れませんでした（引用符が閉じていません）。"
        for found in segments:
            problem = _denied_words(found, denied, depth + 1)
            if problem:
                return problem
    return None


def _command_words(words: list[str]) -> list[str]:
    """前に付いた変数の代入・if/then 等の言葉・後ろのコマンドを動かすだけのもの（env・sudo・xargs 等）を外す。"""
    changed = True
    while words and changed:
        changed = False
        while words and (words[0] in _KEYWORDS or words[0] in _ENDS or _ASSIGNMENT.match(words[0])):
            words = words[1:]
            changed = True
        if words and Path(words[0]).name.lower() in _WRAPPERS:
            valued = _WRAPPERS[Path(words[0]).name.lower()]
            words = words[1:]
            while words and (words[0].startswith("-") or _ASSIGNMENT.match(words[0])):
                words = words[2:] if words[0] in valued else words[1:]
            if words and words[0].replace(".", "").isdigit():   # timeout 10 git …・nice 等の数
                words = words[1:]
            changed = True
    return words


_BREAKS = frozenset(";|&()\n{}")


def _segments(command: str) -> list[list[str]]:
    """コマンドの文字列を、1つずつのコマンドの単語の並びに分ける（区切り ; | & && || 改行 ( ) と、埋め込み $(…)・`…`
    の始まりと終わりで切る）。' の中はそのまま1つの単語。" の中も1つの単語だが、埋め込みの中はコマンドとして読む
    （" の中でも動くので）。"""
    segments: list[list[str]] = [[]]
    word: list[str] | None = None
    i, quote = 0, ""
    embedded: list[list] = []   # 開いている埋め込み：[種類（"$(" か "`"）, 外の引用符, 中の ( の深さ]

    def end_word():
        nonlocal word
        if word is not None:
            segments[-1].append("".join(word))
            word = None

    def end_segment():
        end_word()
        if segments[-1]:
            segments.append([])

    def add(text: str):
        nonlocal word
        word = word if word is not None else []
        word.append(text)

    while i < len(command):
        c = command[i]
        if quote == "'":
            if c == "'":
                quote = ""
            else:
                add(c)
            i += 1
            continue
        if c == "\\" and i + 1 < len(command):
            add(command[i + 1])
            i += 2
            continue
        if c == "$" and command[i + 1:i + 2] == "(" or c == "`" and not (embedded and embedded[-1][0] == "`"):
            end_segment()           # 埋め込みの始まり（" の中でも動く）：中はコマンドとして読む
            embedded.append(["$(" if c == "$" else "`", quote, 0])
            quote = ""
            i += 2 if c == "$" else 1
            continue
        if embedded and not quote and (c == "`" and embedded[-1][0] == "`"
                                       or c == ")" and embedded[-1][0] == "$(" and embedded[-1][2] == 0):
            end_segment()           # 埋め込みの終わり：外の引用符に戻る
            quote = embedded.pop()[1]
            i += 1
            continue
        if quote == '"':
            if c == '"':
                quote = ""
            else:
                add(c)
            i += 1
            continue
        if c in "'\"":
            quote = c
            add("")
            i += 1
            continue
        if embedded and embedded[-1][0] == "$(" and c in "()":
            embedded[-1][2] += 1 if c == "(" else -1
        if c in _BREAKS:
            end_segment()
        elif c.isspace() or c in "<>":   # 書き出し・読み込み：後ろの名前はコマンドではない（単語にして、調べない）
            end_word()
        else:
            add(c)
        i += 1
    if quote or embedded:
        raise ValueError("引用符・埋め込みが閉じていません")
    end_segment()
    return [s for s in segments if s]


def hook_denied(data: str, denied: Denied) -> tuple[int, str]:
    """フックの入力（JSON）のシェルのコマンドを Denied で調べる。(終了コード, stderr に出す文)。止めるときは 2。"""
    try:
        event = json.loads(data or "{}")
    except ValueError:
        return 0, ""
    command = (event.get("tool_input") or {}).get("command") or ""
    problem = check_denied(command, denied) if isinstance(command, str) else None
    return (2, problem) if problem else (0, "")
