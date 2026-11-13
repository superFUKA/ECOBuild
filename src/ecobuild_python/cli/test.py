import os
from pathlib import Path
from typing import Annotated

from ecobuild.errors import EcoBuildError
from ecobuild.execution import added_environment, repeat_tests
from ecobuild_cli.kit import check_repeat, list_tests_like, render_tests, run_command, split_environment

AGENT = "change"


def command(
    *tests: Annotated[str, "流すテスト（ファイル・フォルダ・tests/x.py::test_a。省略すると全部）"],
    filter: Annotated[str, "名前で選ぶ式（pytest の -k。例：\"add and not slow\"）"] = "",
    last_failed: Annotated[bool, "前回失敗したテストだけ流す（pytest の --last-failed。前回の失敗がなければ全部）"] = False,
    list: Annotated[bool, "流せるテストの一覧を出す（流さない。ecobuild tests と同じ）"] = False,
    configuration: Annotated[str, "構成（Debug／Release。既定：ビルド設定の構成、なければDebug）"] = "",
    profile: Annotated[str, "名前付きビルド設定（既定：ecobuild profile use で選んだもの）"] = "",
    env: Annotated[str, "テストの環境に足す環境変数（名前=値。何度でも書ける：--env A=1 --env B=2。その前の venv の用意にも効く）"] = "",
    repeat: Annotated[int, "N 回流す（1回でも失敗したら失敗。--json の result.runs・error.details.runs に回ごとの成否と失敗したケース）"] = 1,
    json: Annotated[bool, "結果をJSONで出力する（テストごとの結果は result.cases。失敗のときは error.details の counts・cases）"] = False,
) -> int:
    """pytest でテストします（venv がなければ作ります）。変えたところのテストだけ流すなら、ファイル等を並べます。

    テストの名前（cases の name）は pytest の nodeid で、そのまま並べて流し直せます。check はいつも全部を流します。
    --list は pytest が集めるテストの一覧を出します（流しません）。
    """
    if list:
        return list_tests_like("", configuration, profile, json)
    environment = split_environment(env, json)
    check_repeat(repeat, json)

    def action(inv):
        module = inv.module
        options, name = module.build_options(configuration, profile or None)
        selected = tuple(_from_root(inv.cwd, module.root, t) for t in tests)
        chosen = [*selected, *([f"-k {filter}"] if filter else []), *(["前回の失敗"] if last_failed else [])]
        inv.info(f"テスト中：{'、'.join(chosen) or '全体'}（{options.configuration}" + (f"、{name}" if name else "")
                 + (f"、{repeat} 回" if repeat > 1 else "") + "）")
        once = rerun_same(lambda chosen, lf: module.type.test(None, options, chosen, filter=filter or None, last_failed=lf),
                          selected, last_failed)
        with added_environment(environment):
            return repeat_tests(once, repeat, lambda n, total: inv.info(f"（{n}/{total} 回目）"))

    narrowed = bool(tests or filter or last_failed)
    return run_command("test", action,
                       lambda r: render_tests(r) if r.passed + r.failed + r.skipped else
                       "当てはまるテストがありません" if narrowed else
                       "テストがありません（ecobuild file add src/<パッケージ>/<名前>.py で、tests/ にテストも作れます）",
                       json_output=json)


def rerun_same(test, tests: tuple[str, ...], last_failed: bool):
    """1回のテスト（--repeat の各回）。test(tests, last_failed) → TestResult。

    --last-failed は、1回目に流したケース（nodeid）を2回目からそのまま流す（pytest の前回の失敗の記録は回ごとに
    書き換わり、1回目で全部通ると2回目から全部を流してしまう）。1回目にケースがなければ、2回目からも同じ指定。"""
    chosen = {"tests": tuple(tests), "last_failed": last_failed}

    def narrow(cases) -> None:
        names = tuple(getattr(c, "name", None) or (c.get("name") if isinstance(c, dict) else None) for c in cases or ())
        if chosen["last_failed"] and names and all(names):
            chosen.update(tests=names, last_failed=False)

    def once():
        try:
            result = test(chosen["tests"], chosen["last_failed"])
        except EcoBuildError as error:
            narrow(error.details.get("cases") if isinstance(error.details, dict) else None)
            raise
        narrow(result.cases)
        return result

    return once


def _from_root(cwd: Path, root: Path, test: str) -> str:
    """今いるディレクトリからの相対で書いたテスト（path[::name]）を、モジュールの root からの相対に（外なら絶対のまま）。"""
    path, sep, rest = test.partition("::")
    absolute = Path(os.path.abspath(cwd / path))
    try:
        path = absolute.relative_to(Path(os.path.abspath(root))).as_posix()
    except ValueError:
        path = absolute.as_posix()
    return path + sep + rest
