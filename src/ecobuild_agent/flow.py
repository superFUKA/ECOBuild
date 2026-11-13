"""流れ（ecobuild flow）の agent の工程：登録したエージェントを、今の作業空間のコンテナで画面なしで動かし（係に頼む。
start_agent(app=True)）、起動の後の返答の終わりを待つ。終わったら、そのエージェントを止める。

    [[steps]]
    id = "impl"
    type = "agent"
    agent = "worker"          # 登録の名前
    prompt = "…"              # 展開してから渡す
    timeout = 3600            # 秒（既定 3600）

結果：`${run.dir}/<工程>.json`（エージェントが書く JSON の表）があれば out に（ok: false なら失敗）。なければ out は空で、
message は最後の返答。pass_if は ecoflow が見る。起動したエージェントの ID・置き場所は工程の覚え書き（data）に残し、
中断から続けるときは、同じエージェントを待ち直す。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import ecoflow
from ecobuild.errors import WorkError

from . import status

DEFAULT_TIMEOUT = 3600
POLL = 3.0             # 様子を見る間（秒）
REPORT_EVERY = 60.0    # 変わりがなくても進み具合を知らせる間（秒）
STOPPED_GRACE = 60.0   # 起動の後、返答なしに止まっていたら失敗とみなすまでの秒数（係が起動している間は起動中）


def kind(module) -> ecoflow.Kind:
    return ecoflow.Kind(lambda step, ctx: run(module, step, ctx), settings=("agent", "prompt"), required=("agent", "prompt"),
                        check=_check, description="登録したエージェントを画面なしで動かし、返答の終わりを待つ")


def _check(settings: dict) -> list[str]:
    if not isinstance(settings.get("agent"), str) or not settings["agent"]:
        return ["agent は登録の名前（文字列）です。"]
    if not isinstance(settings.get("prompt"), str) or not settings["prompt"].strip():
        return ["prompt は文字列です。"]
    return []


def result_path(ctx, step) -> Path:
    return ctx.folder / f"{step.id}.json"


def _prompt(ctx, step) -> str:
    """展開したプロンプト。結果のファイルの場所を書いていなければ、案内を足す。"""
    text = ctx.setting("prompt")
    where = f"{ctx.dir}/{step.id}.json"
    if where in text:
        return text
    return (f"{text.rstrip()}\n\n（終わったら、この工程の結果を {where}（作業空間のルートから）に JSON で書いてください："
            '{"ok": true か false, "message": "短いまとめ"}。ほかの項目も書けます。）')


def run(module, step, ctx, *, sleep=time.sleep, clock=time.time) -> ecoflow.Outcome:
    data = ctx.data
    if not (ctx.resumed and data.get("agent")):
        result_path(ctx, step).unlink(missing_ok=True)   # 前の回の結果を読まない
        name = ctx.setting("agent")
        try:
            record = module.start_agent(name, app=True, prompt=_prompt(ctx, step), progress=ctx.progress)
        except WorkError as error:
            ctx.log(f"起動できません：{error.message}" + (f"\nヒント：{error.hint}" if error.hint else ""))
            return ecoflow.Outcome(ecoflow.FAILED, f"エージェント「{name}」を起動できません：{error.message}",
                                   out={"error": {"code": error.code, "message": error.message, "hint": error.hint}})
        data.update(agent=record.id, folder=str(record.folder), started=clock())
        ctx.save()
        ctx.log(f"エージェント「{record.name}」（{record.id}）を起動しました")
        ctx.progress(f"エージェント「{record.name}」（{record.id}）を起動しました。返答の終わりを待ちます")
    else:
        ctx.progress(f"エージェント {data['agent']} の返答の終わりを待ち直します")
    outcome, reply = _wait(ctx, Path(data["folder"]), float(data["started"]), sleep=sleep, clock=clock)
    _stop(data["agent"], ctx)
    return outcome or _result(ctx, step, reply)


def _wait(ctx, folder: Path, started: float, *, sleep, clock) -> tuple[ecoflow.Outcome | None, str]:
    """返答の終わり（起動より後の replied_at で、待機中か止まっている）まで待つ。(失敗の Outcome か None, 最後の返答)。"""
    limit = ctx.timeout or DEFAULT_TIMEOUT
    told, told_at = None, clock()
    while True:
        if ctx.cancelled():
            return ecoflow.Outcome(ecoflow.FAILED, "取り消しました"), ""
        now = status.activity(folder)
        state, replied = now.get("state"), now.get("replied_at")
        answered = isinstance(replied, (int, float)) and replied > started
        if answered and state in (status.IDLE, status.STOPPED):
            return None, str(now.get("last_reply") or "")
        waited = clock() - started
        if state == status.STOPPED and not answered and waited > STOPPED_GRACE:
            reason = str(now.get("error") or "")
            return ecoflow.Outcome(ecoflow.FAILED, "エージェントが返答せずに止まりました" + (f"：{reason}" if reason else "。")), ""
        if waited > limit:
            return ecoflow.Outcome(ecoflow.FAILED, f"{int(limit)} 秒待っても返答が終わりませんでした。"), ""
        doing = (state, now.get("doing") or "")
        if doing != told or clock() - told_at >= REPORT_EVERY:
            name = status.STATE_NAMES.get(state, state)
            ctx.progress(f"エージェント：{name}" + (f"（{doing[1]}）" if doing[1] else "") + f"・{int(waited // 60)} 分")
            told, told_at = doing, clock()
        sleep(POLL)


def _stop(agent_id: str, ctx) -> None:
    """終わったエージェントを止める（止められなくても工程は終わり。知らせるだけ）。"""
    from . import stop_agent
    try:
        stop_agent(agent_id, progress=ctx.progress)
        ctx.log(f"エージェント {agent_id} を止めました")
    except WorkError as error:
        ctx.log(f"エージェント {agent_id} を止められませんでした：{error.message}")
        ctx.progress(f"注意：エージェント {agent_id} を止められませんでした：{error.message}")


def _result(ctx, step, reply: str) -> ecoflow.Outcome:
    path = result_path(ctx, step)
    if not path.is_file():
        return ecoflow.Outcome(ecoflow.DONE, reply)
    try:
        out = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return ecoflow.Outcome(ecoflow.FAILED, f"結果のファイル {ctx.dir}/{path.name} が読めません：{error}")
    if not isinstance(out, dict):
        return ecoflow.Outcome(ecoflow.FAILED, f"結果のファイル {ctx.dir}/{path.name} は JSON の表（{{…}}）です。")
    message = ecoflow.text_of(out.get("message")) or reply
    if out.get("ok") is False:
        return ecoflow.Outcome(ecoflow.FAILED, message or "エージェントが ok: false を返しました。", out=out)
    return ecoflow.Outcome(ecoflow.DONE, message, out=out)
