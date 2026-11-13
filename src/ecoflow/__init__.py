"""ecoflow：エージェントの流れ（順番・判定・ループ）の汎用の部品。ECOBuild を知らない（ecotask・ecoagent と同じ並び）。

- definition：定義（dict から）の読み込みと確かめ。工程（Step）・結果（Outcome）・工程の種類（Kind）。
- template：`${…}` の展開と、when・pass_if・until の条件（eval は使わない）。
- run：実行の置き場所（Store）・状態（Run。原子的な書き込み・ロック）・状態機械（Engine）。

工程の種類は利用側が登録する（名前 → 関数(step, ctx) → Outcome か Kind）。

    engine = Engine({"echo": lambda step, ctx: Outcome("done", ctx.setting("text"))}, progress=print)
    flow = load({"steps": [{"id": "a", "type": "echo", "text": "${inputs.x}"}], "inputs": {"x": "値"}}, "sample",
                engine.kinds)
    run = engine.start(Store(Path("runs")), flow, {"x": "こんにちは"})
"""

from .definition import Back, Flow, Input, Kind, Outcome, Step, check, load
from .errors import ErrorCode, FlowError
from .template import condition, evaluate, expand, expand_value, text_of
from .run import (CANCELLED, DONE, FAILED, INTERRUPTED, NAMES, PENDING, RUNNING, SKIPPED, WAITING, Context, Engine, Run,
                  Store, inputs_for, lock)

__version__ = "0.1.0"

__all__ = ["Back", "CANCELLED", "Context", "DONE", "Engine", "ErrorCode", "FAILED", "Flow", "FlowError", "INTERRUPTED",
           "Input", "Kind", "NAMES", "Outcome", "PENDING", "RUNNING", "Run", "SKIPPED", "Step", "Store", "WAITING", "check",
           "condition", "evaluate", "expand", "expand_value", "inputs_for", "load", "lock", "text_of"]
