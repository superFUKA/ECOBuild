from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import status as _status
from ecobuild_agent import team as _team

from ...._output import lines, run_command, to_data
from ...workspace.close import render_closed
from . import _forward


def command(*name: Annotated[str, "作業役の名前（か子タスクの番号）。いくつも書けます"],
            merged: Annotated[bool, "提出が取り込み済みの作業役を全員閉じる（名前の代わり）"] = False,
            force: Annotated[bool, "作業中・届いていない言付け・提出の後のコミットがあっても閉じる（GitHub にないものは --discard-local）"] = False,
            discard_local: Annotated[bool, "GitHub にないもの（未コミットの変更・push していないコミット等）も捨てて閉じる"] = False,
            dry_run: Annotated[bool, "閉じられるか・写すファイルを確かめるだけ（閉じない・止めない）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業役の作業空間を閉じます（場所ごと消します）。

    コンテナも消します。閉じる前にエージェントを止め、報告・任された仕事（report.md・brief.md・progress.md）を
    進行役の .ecobuild/ai/team-archive/<番号>-<名前>/ へ写し、受け箱と、まだ届いていないその作業役の知らせを消します。

    取り込みが終わった作業役に使います。GitHub にないもの（未コミットの変更・push していないコミット等）があれば閉じません。
    作業中・届いていない言付けがある・提出の後にコミットがあるときも止めます（--force で閉じる）。
    """
    names = list(name)

    def action(inv):
        chosen = names
        if merged:
            if names:
                raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "名前と --merged は一緒に使えません。")
            chosen = [m.path.name for m in _team.merged_members(inv.module.root, _team.owner_session())]
        elif not names:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "閉じる作業役の名前を書いてください（取り込み済みを全員なら --merged）。")
        if len(chosen) == 1 and not merged:
            return _one(inv, chosen[0])
        closed, failed = [], []
        for one in chosen:
            try:
                closed.append(_one(inv, one))
            except EcoBuildError as error:   # 1人の失敗で残りを止めない
                failed.append({"name": one, "message": error.message, "hint": error.hint, "details": error.details})
        return {"closed": closed, "failed": failed, "dry_run": dry_run}

    def _one(inv, one):
        return close_one(inv, one, force=force, discard_local=discard_local, dry_run=dry_run)

    return run_command("agent team close", action, _render, json_output=json)


def close_one(inv, one: str, *, force: bool = False, discard_local: bool = False, dry_run: bool = False) -> dict:
    """作業役を1人閉じる（係に頼むときは係が閉じる）。結果は JSON にできる形。agent team accept も使う。"""
    flags = [*(["--force"] if force else []), *(["--discard-local"] if discard_local else []),
             *(["--dry-run"] if dry_run else [])]
    return _forward.run(inv, ["agent", "team", "close", one, *flags],
                        lambda inv: _close(inv, one, force=force, discard_local=discard_local, dry_run=dry_run))


def _close(inv, one, *, force: bool, discard_local: bool, dry_run: bool):
    root = inv.module.root
    member = _team.find(root, one, _team.owner_session())
    problems = [] if force else _team.close_problems(member)
    if problems and not dry_run:
        raise EcoBuildError(ErrorCode.UNFINISHED_WORK, f"「{member.name}」はまだ閉じられません。",
                            hint="様子を確かめて（agent team list）、それでも閉じるなら --force。", details=problems)
    pid = _status.running_pid(_team.inbox_of(member.path))
    if pid is not None and not dry_run:   # 動いている作業空間は閉じられない（係を通すときは、係が先に止めている）
        inv.info(f"「{member.name}」のエージェントを止めています…")
        _status.stop(pid)
    module = type(inv.module)
    try:
        preview = module.close_workspace(member.path, discard_local=discard_local, dry_run=True)
    except EcoBuildError as error:
        if dry_run and error.code == ErrorCode.WORKSPACE_LOCKED and pid is not None:   # 閉じるときに止めるもの
            preview, problems = None, [*problems, f"「{member.name}」のエージェントが動いています（閉じるときに止めます）"]
        else:   # GitHub にないもの：どのファイルかも見せる
            files = _team.unpushed_files(member)
            raise EcoBuildError(error.code, f"「{member.name}」を閉じられません：{error.message}", hint=error.hint,
                                details=[*(error.details or ()), *(f"ファイル：{path}" for path in files)]) from error
    if dry_run:
        kept = [f"{_team.ARCHIVE}/{member.path.name}/{p.rsplit('/', 1)[-1]}" for p in _team.KEPT
                if (member.path / p).is_file()]
        return {"path": str(member.path), "done": False, "removed": False, "left": [], "name": member.name,
                "problems": problems, "archive": kept}
    kept = _team.archive(root, member)
    result = to_data(module.close_workspace(member.path, discard_local=discard_local))
    _team.forget_member(root, member)
    return {**result, "name": member.name, "archive": kept, "problems": []}


def _render(r) -> str:
    if "closed" in r:
        return lines(*(_render(one) for one in r["closed"]),
                     *(f"「{f['name']}」は閉じませんでした：{f['message']}" for f in r["failed"]),
                     "閉じる作業役はいません。" if not r["closed"] and not r["failed"] else None)
    return lines(
        render_closed(_Closed(r)),
        *(f"止めるわけ：{p}（--force で閉じる）" for p in r.get("problems") or ()),
        f"写したもの：{'、'.join(r['archive'])}" if r.get("archive") else None,
    )


class _Closed:
    """render_closed に渡す形（結果は dict）。"""
    def __init__(self, data: dict):
        self.__dict__.update(data)
