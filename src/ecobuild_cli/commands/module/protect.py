from typing import Annotated

from ..._output import lines, run_command, usage_error


def render_protection(p) -> str:
    if p is None:
        return "ブランチの保護はありません（ecobuild module protect で設定できます）"
    return lines(
        f"{p.branch} は保護されています：取り込みは提出だけ"
        + (f"・承認 {p.approvals} 人" if p.approvals else "・承認は不要"),
        f"  通っている必要がある CI：{', '.join(p.checks)}" if p.checks else None,
        "  強制 push：" + ("できる" if p.allow_force_pushes else "できない")
        + "・管理者：" + ("守る" if p.enforce_admins else "越えられる（ECOBuild の task finish は、承認の数を満たすまで止まります）"),
    )


def command(
    approvals: Annotated[int, "取り込みに要る承認の数（既定：[task] require_approval なら1、なければ0）"] = -1,
    require_ci: Annotated[bool, "作成元の最新のコミットの CI の項目が通っていることも必須にする"] = False,
    show: Annotated[bool, "今の設定を表示するだけにする"] = False,
    off: Annotated[bool, "ブランチの保護を外す"] = False,
    yes: Annotated[bool, "確認せずに実行する"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """作成元のブランチ（default_base）を、GitHub のブランチの保護で守ります（複数人での開発向け）。

    ECOBuild の手元のフックだけでなく、GitHub でも、提出（PR）以外での変更・強制 push・削除を止めます。
    承認の数を決められます。GitHub の無料プランの非公開リポジトリでは使えません。
    """
    if sum([show, off]) > 1 or ((show or off) and (approvals >= 0 or require_ci)):
        return usage_error("--show・--off は、他のオプションと一緒に指定できません。", json)

    def action(inv):
        module = inv.module
        if show:
            return module.protection()
        if off:
            inv.confirm(f"{module.config.default_base} のブランチの保護を外しますか？")
            return {"removed": module.unprotect()}
        inv.confirm(f"GitHub で {module.config.default_base} のブランチの保護を設定しますか？（提出以外で変更できなくなります）")
        return module.protect(approvals=None if approvals < 0 else approvals, require_ci=require_ci)

    def render(r):
        if isinstance(r, dict):
            return "ブランチの保護を外しました" if r["removed"] else "ブランチの保護はありませんでした"
        return render_protection(r)

    return run_command("module protect", action, render, json_output=json, yes=yes)
