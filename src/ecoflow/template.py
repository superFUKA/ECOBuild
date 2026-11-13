"""`${…}` の展開と、when・pass_if・until の条件（eval は使わない）。

名前：`${inputs.x}`・`${vars.x}`・`${steps.<id>.message}`・`${steps.<id>.out.x}`・`${steps.<id>.prev_out.x}`（前の回）・
`${out.x}`・`${run.id}`・`${run.dir}`・`${run.flow}`。ない名前は空文字。`$${` は `${` そのもの。
条件：
- `a == b`・`a != b`：両方が数として読めれば数で、そうでなければ文字で比べる。
- `>=`・`<=`・`>`・`<`：両方が数のときだけ比べる（片方でも数でなければ偽）。数は 10・-1.5・1e3 の形だけ
  （1_0・inf・nan は数にしない）。
- `x`：空・0・false・no・空の配列・空の表でなければ真。`!x`：その逆。
- `&&`・`||`・かっこ。強さは 比べ ＞ `!` ＞ `&&` ＞ `||`（`!a == b` は `!(a == b)`）。
- 値は `${…}`・引用符の文字（'…'・"…"。中の `${…}` は展開しないので書けない）・そのままの語。
- 長さは LIMIT 字、入れ子は DEPTH まで。
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

ROOTS = ("inputs", "vars", "steps", "out", "run")
RUN_NAMES = ("id", "dir", "flow")
_REFERENCE = re.compile(r"\$\$\{|\$\{([^{}]*)\}")
_FALSE = ("", "0", "false", "no")
_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
LIMIT = 2000
DEPTH = 64


def references(text: str) -> list[str]:
    """文の中の `${…}` の名前（中の空白は除く）。"""
    return [match.group(1).strip() for match in _REFERENCE.finditer(text) if match.group(1) is not None]


def unclosed(text: str) -> bool:
    """閉じていない `${` があるか。"""
    return "${" in _REFERENCE.sub("", text)


def lookup(scope: dict, name: str) -> Any:
    """名前（a.b.c）の値。ない名前は None。"""
    value: Any = scope
    for part in name.strip().split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def text_of(value: Any) -> str:
    """値を文にする（None は空、真偽は true・false、dict・list は JSON）。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def expand(text: str, scope: dict) -> str:
    """文の `${…}` を値に置き換える。"""
    return _REFERENCE.sub(lambda m: "${" if m.group(1) is None else text_of(lookup(scope, m.group(1))), text)


def expand_value(value: Any, scope: dict) -> Any:
    """文・list・dict の中の文をすべて展開する（ほかの値はそのまま）。"""
    if isinstance(value, str):
        return expand(value, scope)
    if isinstance(value, list):
        return [expand_value(item, scope) for item in value]
    if isinstance(value, dict):
        return {key: expand_value(item, scope) for key, item in value.items()}
    return value


def strings(value: Any) -> list[str]:
    """値の中の文をすべて（定義の確かめで、`${…}` を探すため）。"""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in strings(item)]
    return []


def truthy(value: Any) -> bool:
    """値が真か（空・0・false・no・空の配列・空の表でなければ真）。"""
    if isinstance(value, (list, dict)):
        return bool(value)
    number = number_of(value)
    if number is not None:
        return number != 0
    return text_of(value).strip().lower() not in _FALSE


def number_of(value: Any) -> float | None:
    """数として読めればその数（真偽・inf・nan・1_0 等は数にしない）。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str) and _NUMBER.match(value.strip()):
        return float(value.strip())
    return None


# ---- 条件 -------------------------------------------------------------------------------------------------
_COMPARISONS = ("==", "!=", ">=", "<=", ">", "<")
_TOKEN = re.compile(r"""\s*(?:(?P<ref>\$\{[^{}]*\})|(?P<quoted>'[^']*'|"[^"]*")|(?P<op>==|!=|>=|<=|&&|\|\||[><!()])"""
                    r"""|(?P<word>[^\s()!=<>&|'"]+))""")


@dataclass(frozen=True)
class _Operand:
    kind: str      # ref・text
    value: str


@dataclass(frozen=True)
class _Node:
    op: str        # value・not・and・or・比べ方
    items: tuple


class Condition:
    """読んだ条件。evaluate(scope) で真偽。"""

    def __init__(self, text: str):
        self.text = text
        if len(text) > LIMIT:
            raise ValueError(f"条件が長すぎます（{LIMIT} 字まで）。")
        self._tokens = _tokens(text)
        self._at = 0
        self._depth = 0
        if not self._tokens:
            raise ValueError("条件が空です。")
        self._root = self._or()
        if self._at < len(self._tokens):
            raise ValueError(f"条件「{text}」の「{self._tokens[self._at][1]}」が読めません。")

    @property
    def references(self) -> list[str]:
        return references(self.text)

    def evaluate(self, scope: dict) -> bool:
        return self._truth(self._root, scope)

    # 読み方：or := and ('||' and)*、and := not ('&&' not)*、not := '!' not | cmp、cmp := atom (比べ方 atom)?
    def _peek(self) -> tuple[str, str] | None:
        return self._tokens[self._at] if self._at < len(self._tokens) else None

    def _take(self) -> tuple[str, str]:
        token = self._peek()
        if token is None:
            raise ValueError(f"条件「{self.text}」が途中で終わっています。")
        self._at += 1
        return token

    def _deeper(self) -> None:
        self._depth += 1
        if self._depth > DEPTH:
            raise ValueError(f"条件の入れ子が深すぎます（{DEPTH} まで）。")

    def _or(self) -> _Node:
        self._deeper()
        items = [self._and()]
        while self._peek() == ("op", "||"):
            self._take()
            items.append(self._and())
        self._depth -= 1
        return items[0] if len(items) == 1 else _Node("or", tuple(items))

    def _and(self) -> _Node:
        items = [self._not()]
        while self._peek() == ("op", "&&"):
            self._take()
            items.append(self._not())
        return items[0] if len(items) == 1 else _Node("and", tuple(items))

    def _not(self) -> _Node:
        if self._peek() == ("op", "!"):
            self._take()
            self._deeper()
            inner = self._not()
            self._depth -= 1
            return _Node("not", (inner,))
        return self._comparison()

    def _comparison(self) -> _Node:
        left = self._atom()
        token = self._peek()
        if token is not None and token[0] == "op" and token[1] in _COMPARISONS:
            self._take()
            return _Node(token[1], (left, self._atom()))
        return left

    def _atom(self) -> _Node:
        kind, text = self._take()
        if (kind, text) == ("op", "("):
            inner = self._or()
            if self._take() != ("op", ")"):
                raise ValueError(f"条件「{self.text}」のかっこが閉じていません。")
            return inner
        if kind == "op":
            raise ValueError(f"条件「{self.text}」の「{text}」の前に値がありません。")
        if kind == "ref":
            return _Node("value", (_Operand("ref", text[2:-1].strip()),))
        if kind == "quoted":
            if "${" in text:
                raise ValueError(f"条件「{self.text}」：引用符の中の ${{…}} は展開しません（引用符の外に書きます）。")
            return _Node("value", (_Operand("text", text[1:-1]),))
        if "${" in text:
            raise ValueError(f"条件「{self.text}」の「{text}」が読めません（${{…}} は閉じて、語と分けて書きます）。")
        return _Node("value", (_Operand("text", text),))

    def _value(self, node: _Node, scope: dict) -> Any:
        if node.op == "value":
            operand = node.items[0]
            return lookup(scope, operand.value) if operand.kind == "ref" else operand.value
        if node.op == "not":
            return not self._truth(node.items[0], scope)
        if node.op == "and":
            return all(self._truth(item, scope) for item in node.items)
        if node.op == "or":
            return any(self._truth(item, scope) for item in node.items)
        return _compare(node.op, self._value(node.items[0], scope), self._value(node.items[1], scope))

    def _truth(self, node: _Node, scope: dict) -> bool:
        value = self._value(node, scope)
        return truthy(value) if node.op == "value" else bool(value)


def _tokens(text: str) -> list[tuple[str, str]]:
    found, at = [], 0
    text = text.strip()
    while at < len(text):
        match = _TOKEN.match(text, at)
        if match is None or match.end() == at:
            raise ValueError(f"条件「{text}」の「{text[at:].strip()[:20]}」が読めません。")
        kind = match.lastgroup
        found.append((kind, match.group(kind)))
        at = match.end()
        while at < len(text) and text[at].isspace():
            at += 1
    return found


def _compare(op: str, left: Any, right: Any) -> bool:
    a, b = number_of(left), number_of(right)
    if a is None or b is None:
        if op not in ("==", "!="):
            return False   # 大小は数どうしだけ
        a, b = text_of(left), text_of(right)
    return {"==": a == b, "!=": a != b, ">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b}[op]


def condition(text: str) -> Condition:
    """条件を読む（読めなければ ValueError。文は利用者に見せられる日本語）。"""
    return Condition(text)


def evaluate(text: str, scope: dict) -> bool:
    return Condition(text).evaluate(scope)
