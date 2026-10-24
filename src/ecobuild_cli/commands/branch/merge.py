from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode

from ..._output import run_command

_METHODS = {"fast-forward": "早送り", "merge": "マージコミット", "conflict": "衝突する", "up-to-date": "取り込み済み"}


def command(
    name: Annotated[str, "取り込むブランチ"],
    into: Annotated[str, "取り込み先のブランチ。付けると提出（PR）なしで直接取り込む"] = "",
    dry_run: Annotated[bool, "--into の取り込みを前もって確かめるだけ（入るコミット・変わるファイル・衝突。何も変えない）"] = False,
    ignore_checks: Annotated[bool, "CIが失敗していても取り込む（提出を取り込むとき）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """ブランチ同士（タスクブランチでないブランチ）を取り込みます。

    --into <先> を付けると、name を先のブランチへ直接取り込みます（提出〔PR〕を作りません。早送りできれば早送り、
    できなければマージコミット。衝突したら何も変えずに止めます。衝突したのが自動で作るファイル〔型の生成ファイル〕だけなら、
    合わさった管理ファイルから作り直して取り込みます）。--dry-run を足すと、取り込む前に、入るコミット・
    変わるファイル・方法・衝突するファイル・取り込める人を表示します。--into を付けなければ、ecobuild branch submit
    で作った提出を、マージコミットで取り込みます。
    """
    if dry_run:
        def plan(inv):
            if not into:
                raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--dry-run は --into と一緒に使います。",
                                    hint=f"ecobuild branch merge {name} --into <取り込み先> --dry-run")
            return inv.module.repository.plan_branch_merge(name, into)
        return run_command("branch merge", plan, _render_plan, json_output=json)
    if into:
        return run_command("branch merge", lambda inv: inv.module.repository.merge_branch_into(name, into),
                           lambda r: f"{name} を {into} へ取り込みました（{r.method}・{r.commit[:7]}）"
                                     + (f"。衝突した自動で作るファイルは作り直しました：{'、'.join(r.resolved)}" if r.resolved else ""),
                           json_output=json)
    return run_command("branch merge", lambda inv: inv.module.repository.merge_branch(name, ignore_checks=ignore_checks),
                       lambda r: f"{name} の提出を取り込みました（{r.method}）", json_output=json)


def _render_plan(p) -> str:
    lines = [f"{p.name} → {p.into}：{_METHODS.get(p.method, p.method)}（入るコミット {p.commit_count} 件・変わるファイル {p.file_count} 件）"]
    lines += [f"  {c.sha[:7]} {c.subject}" for c in p.commits]
    if p.commit_count > len(p.commits):
        lines.append(f"  ……ほか {p.commit_count - len(p.commits)} 件")
    if p.resolved:
        lines.append("衝突する自動で作るファイル（取り込むときに作り直します）：")
        lines += [f"  {f}" for f in p.resolved]
    if p.conflicts:
        lines.append("衝突するファイル：")
        lines += [f"  {f}" for f in p.conflicts]
    if not p.allowed:
        lines.append(f"取り込めるのは {p.owners} です。")
    return "\n".join(lines)
