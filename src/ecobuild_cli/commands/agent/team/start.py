from pathlib import Path
from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import team as _team

from ...._output import lines, run_command
from ...container._source import source
from . import _forward


def command(name: Annotated[str, "名前（子タスクの題名・タスクブランチの名前にもなる。日本語も使えます）"],
            brief: Annotated[str, "任せる仕事：目的・返してほしいもの・使ってよい道具・範囲（やらないこと）"] = "",
            brief_file: Annotated[str, "任せる仕事を書いたファイル（--brief の代わり）"] = "",
            manager: Annotated[bool, "作業役ではなく、管理役を作る（進行役が、自分の下に1人だけ作る。作業役は管理役が作る）"] = False,
            model: Annotated[str, "この作業役のモデル（既定はこのPCの設定 agent_worker_model・agent_manager_model）"] = "",
            no_open: Annotated[bool, "作るだけで起動しない（係・GUI が起動するとき）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業役（--manager なら管理役）を作って起動します（作業役は管理役が、管理役は進行役が使います）。

    進行役のタスクの子タスク（題名 名前・本文 任せる仕事）と、そのタスクブランチを置いた作業空間
    （.ecobuild/ai/team/<番号>-<名前>/）を作り、任せる仕事を .ecobuild/ai/brief.md に置いて、作業役を起動します。
    作業役は終わったら .ecobuild/ai/report.md に報告を書き、進行役のタスクブランチへ提出します。
    """
    def action(inv):
        if brief_file and brief:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--brief と --brief-file は一緒に使えません。")
        text = Path(brief_file).read_text(encoding="utf-8") if brief_file else brief
        args = ["agent", "team", "start", name, "--brief", text, *(["--manager"] if manager else []),
                *(["--model", model] if model else []), "--no-open"]
        return _forward.run(inv, args, lambda inv: _create(inv, text))

    def _create(inv, text):
        member = _team.create(inv.module, name, text, role=_team.MANAGER if manager else _team.WORKER, model=model,
                              progress=inv.info)
        if no_open:
            return member
        from ...._module import Module
        Module.find(member.path).start_agent(source=source(), progress=inv.info, role=member.role, prompt=member.prompt)
        return _team.Member(**{**member.__dict__, "opened": True})

    return run_command("agent team start", action, _render, json_output=json)


def _render(r) -> str:
    role = _team.ROLE_NAMES.get(r.get("role"), "作業役")
    return lines(
        f"{role}「{r.get('name')}」を作りました：子タスク #{r.get('task')}（{r.get('branch')}）、作業空間 {_forward.place(r)}",
        f"モデル：{r.get('model')}" if r.get("model") else None,
        f"新しい画面で起動しました" if r.get("opened") else None,
        "係が画面なしで起動しました（様子は agent team list・agent team log で）" if r.get("app") else None,
        r.get("note") or None,
        f"報告は {_forward.place(r)}/{_team.REPORT_FILE} に書かれます。返答が終わると知らせが届きます（係）。",
    )
