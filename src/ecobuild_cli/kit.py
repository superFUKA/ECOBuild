"""型の拡張のコマンド（ecobuild_<型>.cli）が使う、CLI の補助（公開）。

型ごとのコマンドは、型の拡張の cli パッケージに CLIFrameWork の形（1ファイル1コマンド、def command）で書く。
ここには、その中身として使う共通の処理（結果の表示・JSON・終了コード、型によらないビルド・ファイルの操作）を置く。
オプションと説明は型ごとのファイルが決め、ここは受け取った値で本体（Module）を呼ぶだけ。
"""

from __future__ import annotations

import os
from pathlib import Path

from ecobuild.errors import EcoBuildError

from . import _events
from ._output import (
    Invocation, build_like, lines, missing, optional_argument, run_command, split_list, split_numbers,
    split_semicolons, usage_error,
)

__all__ = [
    "Invocation", "ProgramOutput", "add_files", "build_like", "lines", "missing", "move_file",
    "optional_argument", "remove_files", "render_profiles", "run_command", "run_like", "split_list", "split_numbers",
    "split_semicolons", "test_like", "usage_error",
]


class ProgramOutput:
    """ツール・プログラムの出力を流す口（呼ぶたびに文字列。部分的な行〔入力の催促〕もすぐ流す）。

    --json では標準エラーへ、1行ずつ output のイベントで（_events。stream：プログラムの stdout・stderr、source：
    program〔実行するプログラム〕・tool〔ビルド・テストのツール〕。標準出力は最後の JSON だけ。出力の全部は今までどおり
    result・error.details に入る）。人向けにはそのまま（stdout は標準出力へ、stderr は標準エラーへ）。いくつかの
    スレッド（stdout・stderr）から呼んでよい。
    """

    def __init__(self, json_output: bool, source: str = "program"):
        self.json_output = json_output
        self.source = source

    def __call__(self, text: str, stream: str = "stdout", source: str | None = None) -> None:
        _events.output(text, self.json_output, stream=stream, source=source or self.source)

    def line(self, text: str, stream: str = "stdout", source: str | None = None) -> None:
        """1行（改行なし）。"""
        self(text + "\n", stream, source)


def test_like(project: str, configuration: str, profile: str, json_output: bool, *, empty: str,
              tests: tuple[str, ...] = ()) -> int:
    """test の共通の入口。empty：テストが1件もないときの表示（型ごとに次の一手が違う）。
    tests：流すテスト（今いるディレクトリからの相対。:: の後ろはそのまま）。モジュールの root からの相対にして渡す。"""

    def action(inv):
        module = inv.module
        target = project or module.project_at(inv.cwd)
        options, name = module.build_options(configuration, profile or None)
        selected = tuple(_from_root(inv.cwd, module.root, t) for t in tests)
        inv.info(f"テスト中：{target or ('、'.join(selected) if selected else '全体')}（{options.configuration}"
                 + (f"、{name}" if name else "") + "）")
        return module.test(project=target, configuration=configuration, profile=profile or None, tests=selected)

    return run_command("test", action,
                       lambda r: f"テスト：成功 {r.passed}、失敗 {r.failed}、スキップ {r.skipped}"
                       if r.passed + r.failed + r.skipped or project else empty,
                       json_output=json_output)


def _from_root(cwd: Path, root: Path, test: str) -> str:
    """今いるディレクトリからの相対で書いたテスト（path[::name]）を、モジュールの root からの相対に（外なら絶対のまま）。"""
    path, sep, rest = test.partition("::")
    absolute = Path(os.path.abspath(cwd / path))
    try:
        path = absolute.relative_to(Path(os.path.abspath(root))).as_posix()
    except ValueError:
        path = absolute.as_posix()
    return path + sep + rest


def run_like(project: str, configuration: str, profile: str, arguments: str, json_output: bool, *,
             streamed: bool = False) -> int:
    """run の共通の入口（プログラムの出力は人向けにはそのまま、--json では result.output）。

    streamed：プログラムの出力を実行中に流している（ProgramOutput）。人向けには終わってからもう一度は出さない。"""

    def action(inv):
        module = inv.module
        target = project or module.executable_at(inv.cwd)
        try:
            return module.run(project=target, configuration=configuration, profile=profile or None,
                              arguments=arguments)
        except EcoBuildError as error:
            if streamed and not json_output and isinstance(error.details, dict) and "output" in error.details:
                error.details["output"] = "（出力は上に流しました）"
            raise

    return run_command("run", action, (lambda r: None) if streamed and not json_output else lambda r: r.output,
                       json_output=json_output)


def add_files(paths: tuple[str, ...], test: bool, template: str, json_output: bool) -> int:
    """file add の共通の入口。"""

    def action(inv):
        changed = inv.module.add_files([inv.cwd / path for path in paths], test=test, template=template or None)
        return {"paths": [p for c in changed for p in c.paths]}

    return run_command("file add", action, lambda r: "追加しました：\n" + "\n".join(f"  {p}" for p in r["paths"]),
                       json_output=json_output)


def move_file(source: str, destination: str, test: bool, json_output: bool) -> int:
    """file move の共通の入口。"""

    def action(inv):
        return inv.module.move_file(inv.cwd / source, inv.cwd / destination, test=test)

    def render(r):
        pairs = zip(r.paths[0::2], r.paths[1::2])
        return "移動しました：\n" + "\n".join(f"  {a} → {b}" for a, b in pairs) \
            + ("\n読み込み（#include）を直しました：\n" + "\n".join(f"  {p}" for p in r.edited) if r.edited else "")

    return run_command("file move", action, render, json_output=json_output)


def remove_files(paths: tuple[str, ...], test: bool, json_output: bool) -> int:
    """file remove の共通の入口。"""

    def action(inv):
        changed = [inv.module.remove_file(inv.cwd / path, test=test) for path in paths]
        return {"paths": [p for c in changed for p in c.paths]}

    return run_command("file remove", action, lambda r: "削除しました：\n" + "\n".join(f"  {p}" for p in r["paths"]),
                       json_output=json_output)


def _values(values: dict) -> str:
    return "、".join(f"{key}={value}" for key, value in values.items())


def render_profiles(r) -> str:
    """ビルド設定の一覧（profile list・use・remove・add 等の結果）。"""
    if not r.profiles:
        return "ビルド設定はありません（ecobuild profile add で追加できます）"
    rows = []
    for name, p in r.profiles.items():
        rows.append(("* " if name == r.selected else "  ")
                    + f"{name}：{p.configuration}" + ("、共有ライブラリ" if p.shared else "") + f"、並列 {p.parallel}"
                    + (f"、{_values(p.options)}" if p.options else ""))
        rows += [f"      {project}：{_values(values)}" for project, values in p.projects.items()]
    return "\n".join(rows)
