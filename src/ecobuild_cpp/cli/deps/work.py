from typing import Annotated

from ecobuild_cli.kit import run_command

AGENT = "change"   # 手元の clone（deps/<名前>）を切り替えるだけ。GitHub・記録は変えない

ORIGINS = {"local": "このPCの作業空間", "github": "GitHub"}


def command(
    name: Annotated[str, "依存先の名前（deps list の名前）"],
    task: Annotated[int, "依存先のリポジトリのタスク（Issue）の番号：そのタスクブランチ（task/<番号>-…）の最新にする"] = 0,
    branch: Annotated[str, "依存先の任意のブランチの最新にする（--task の代わりに）"] = "",
    done: Annotated[bool, "作業版をやめ、記録の版に戻す（deps sync と同じ）"] = False,
    json: Annotated[bool, "結果をJSONで出力する"] = False,
) -> int:
    """依存先の手元の clone を、作りかけの版（依存先のタスクブランチの最新）にします（作業版）。

    依存先のモジュールで作っている途中のもの（push していないコミットも）を、このモジュールで build・test して試せます。
    このPCに依存先のモジュールがあり、そのタスクの作業空間があれば、そこから取ります（なければ GitHub のタスクブランチ
    から。push 済みのものだけ）。記録の版は変えません（コミットしません）。作業版のまま build・test すると「手元の版が
    記録と違う」と知らせます。提出の前の確かめ・CI は記録の版を使うので、記録の版でも通る必要があります。

    --task・--branch を省くと、今の作業版を取り直します（依存先の側が進んだら）。依存先を直すのは、依存先のモジュールの
    タスク（その作業空間）でします。deps/ の中ではコミットしません。依存先のタスクが取り込まれたら、--done で作業版を
    やめ、ecobuild deps update <依存先> で記録を進めます。deps update --at に push していないコミットは渡せません。

    例：
      ecobuild deps work Engine --task 12
      ecobuild deps work Engine
      ecobuild deps work Engine --done
    """
    return run_command("deps work", lambda inv: inv.module.work_dependency(name, task=task or None, branch=branch or None,
                                                                           done=done),
                       _text, json_output=json)


def work_text(name: str, work) -> str:
    """作業版の説明：「Engine #12・このPCの作業空間、task/12-fg」。"""
    notes = [f"{name} #{work.task}" if work.task is not None else "", ORIGINS.get(work.origin or "", "")]
    head = "・".join(n for n in notes if n)
    return f"{head}、{work.branch}" if head else work.branch


def _text(r) -> str:
    if r.action == "done":
        text = f"{r.name}：作業版をやめ、記録の版 {r.recorded[:7]} に戻しました。"
        others = [c for c in r.changes if c.name != r.name and c.action != "unchanged"]
        return text + "".join(f"\n{c.name}：{c.action}" + (f"（{c.reason}）" if c.reason else "") for c in others)
    commit = (r.work.commit or "")[:7]
    head = {"switched": "作業版にしました", "refreshed": "作業版を取り直しました",
            "unchanged": "作業版を取り直しました（変わっていません）"}.get(r.action, r.action)
    lines = [f"{r.name}：{head}（{work_text(r.name, r.work)} {commit}）。記録の版 {r.recorded[:7]} は変えていません。"]
    lines += [f"{c.name}：{c.action}（作業版が使う依存先）" for c in r.changes]
    lines.append("build・test は作業版で行います（「手元の版が記録と違う」と知らせます）。提出の前の確かめ・CI は記録の版を"
                 "使うので、依存先のタスクが取り込まれたら --done で戻し、ecobuild deps update で記録を進めてください。")
    return "\n".join(lines)
