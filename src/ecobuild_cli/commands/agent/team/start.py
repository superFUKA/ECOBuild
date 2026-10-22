from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_agent import serve as _serve
from ecobuild_agent import team as _team

from ...._output import lines, run_command, to_data
from ...container._source import source
from . import _forward

BRIEF_SUFFIXES = (".md", ".txt")   # --brief-dir で読むファイル（ファイル名が名前）


def command(*name: Annotated[str, "名前（子タスクの題名・タスクブランチの名前にもなる。日本語も使えます。--brief-dir なら要らない）"],
            brief: Annotated[str, "任せる仕事：目的・返してほしいもの・使ってよい道具・範囲（やらないこと）"] = "",
            brief_file: Annotated[str, "任せる仕事を書いたファイル（--brief の代わり）"] = "",
            brief_dir: Annotated[str, "1人1ファイルの任せる仕事を置いたフォルダー（ファイル名〔.md・.txt を除く〕が名前。全員を並べて作る）"] = "",
            manager: Annotated[bool, "作業役ではなく、管理役を作る（進行役が仕事ごとに、管理役が大きな部分ごとに作る。作業役は管理役が作る）"] = False,
            report_only: Annotated[bool, "報告だけの作業役にする（調べもの・レビュー。ファイルを変えず・提出しない）"] = False,
            task: Annotated[int, "子タスクを新しく作らず、この番号の子タスク（作業空間がないもの）から作る"] = 0,
            model: Annotated[str, "この作業役のモデル（既定はこのPCの設定 agent_worker_model・agent_manager_model）"] = "",
            no_open: Annotated[bool, "作るだけで起動しない（係・GUI が起動するとき）"] = False,
            json: Annotated[bool, "結果をJSONで出力する"] = False) -> int:
    """作業役（--manager なら管理役）を作って起動します（作業役は管理役が、管理役は進行役と管理役が使います）。

    今のタスクの子タスク（題名 名前・本文 任せる仕事）と、そのタスクブランチを置いた作業空間
    （.ecobuild/ai/team/<番号>-<名前>/）を作り、任せる仕事を .ecobuild/ai/brief.md に置いて、作業役を起動します。
    作業役は終わったら .ecobuild/ai/report.md に報告を書き、管理役のタスクブランチへ提出します（--report-only なら
    提出せず、agent report で知らせます）。GitHub の一時的な失敗は、待ってやり直します。
    """
    def action(inv):
        if sum(map(bool, (brief, brief_file, brief_dir))) > 1:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--brief・--brief-file・--brief-dir は1つだけ使えます。")
        if brief_dir:
            if name or task:
                raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "--brief-dir では名前・--task は書きません（ファイル名が名前です）。")
            return _many(inv)
        if len(name) != 1:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, "名前を1つ書いてください（何人も作るなら --brief-dir）。")
        text = Path(brief_file).read_text(encoding="utf-8-sig") if brief_file else brief   # メモ帳等の BOM を brief・Issue に入れない
        return _one(inv, name[0], text)

    def _one(inv, one, text, module=None):
        args = ["agent", "team", "start", one, "--brief", text, *(["--manager"] if manager else []),
                *(["--report-only"] if report_only else []), *(["--task", str(task)] if task else []),
                *(["--model", model] if model else []), "--no-open"]
        return _forward.run(inv, args, lambda inv: _create(inv, one, text, module or inv.module))

    def _many(inv):
        folder = Path(brief_dir)
        files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in BRIEF_SUFFIXES) \
            if folder.is_dir() else []
        if not files:
            raise EcoBuildError(ErrorCode.INVALID_ARGUMENT, f"{brief_dir} に任せる仕事のファイル（.md・.txt）がありません。")
        made, failed = [], []

        def one(file):
            try:   # 1人ずつ別の Module で（並べて作る。係を通すときは、係が数人ずつ並べる）
                module = type(inv.module).find(inv.module.root)
                made.append(_one(inv, file.stem, file.read_text(encoding="utf-8-sig"), module))
            except EcoBuildError as error:
                failed.append({"name": file.stem, "message": error.message, "hint": error.hint, "details": error.details})
        with ThreadPoolExecutor(max_workers=_serve.START_LIMIT) as pool:
            list(pool.map(one, files))
        order = {file.stem: index for index, file in enumerate(files)}
        made.sort(key=lambda m: order.get(m.get("name"), 0))
        return {"members": made, "failed": failed}

    def _create(inv, one, text, module):
        member = _team.create(module, one, text, role=_team.MANAGER if manager else _team.WORKER, model=model,
                              existing=task, report_only=report_only, progress=inv.info)
        if no_open:
            return member
        from ...._module import Module
        Module.find(member.path).start_agent(source=source(), progress=inv.info, role=member.role, prompt=member.prompt)
        return _team.Member(**{**member.__dict__, "opened": True})

    return run_command("agent team start", action, _render, json_output=json)


def _render(r) -> str:
    if "members" in r:
        return lines(*(_render(m) for m in r["members"]),
                     *(f"「{f['name']}」は作れませんでした：{f['message']}" + (f"（{f['hint']}）" if f.get("hint") else "")
                       for f in r["failed"]))
    r = to_data(r)
    role = _team.ROLE_NAMES.get(r.get("role"), "作業役")
    return lines(
        f"{role}「{r.get('name')}」を作りました：子タスク #{r.get('task')}（{r.get('branch')}）、作業空間 {_forward.place(r)}",
        f"モデル：{r.get('model')}" if r.get("model") else None,
        f"新しい画面で起動しました" if r.get("opened") else None,
        "係が画面なしで起動しました（様子は agent team list・agent team log で）" if r.get("app") else None,
        r.get("note") or None,
        f"報告は {_forward.place(r)}/{_team.REPORT_FILE} に書かれます。返答が終わると知らせが届きます（係）。",
    )
