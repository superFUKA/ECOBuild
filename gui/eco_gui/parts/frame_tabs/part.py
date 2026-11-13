"""モジュールの窓の、作業空間のタブ。作業空間ごとに1つ（題：タスクの題と小さく #n。提出の確認中は「#n の提出を確認中」）。

× でタブを閉じる（作業空間は残る。閉じたタブは、窓を開いているあいだ閉じたまま：ほかのページへ行って戻っても・読み直しても。memory.session）。
タブはドラッグで並べ替える（モジュールごとに、この PC に覚える）。右の ▼ で作業空間の一覧（閉じたタブをまた出す・作業空間を削除）。タブの右クリックでメニュー
（閉じる・他を閉じる・エクスプローラー・Visual Studio・状態を更新・作業空間を削除・タスクを表示）。←→・Home・End で移り、Delete で閉じる。
出ているタブが1つもないときは、案内（「表示中の作業空間はありません」）を出す。

選んでいるタブがない・なくなった（閉じた・作業空間が消えた）ときは、出ているタブの先頭（最後に見ていたものがあれば、それ）を
選んだことにして出力する（1つもなければ emptied）。どのタブを見せるかだけを決め、することは画面のつなぎが決める。"""
from typing import Annotated


def part(
    workspaces: Annotated[list[dict] | None, "作業空間（ecobuild module show の workspaces：name・path・branch・task・review）。まだ読めていなければ None"] = None,
    tasks: Annotated[list[dict] | None, "タスク（ecobuild task list：number・title）。タブの題に使う"] = None,
    current: Annotated[str, "今出している作業空間の場所（なければ空）"] = "",
    module: Annotated[str, "モジュールのフォルダー（閉じたタブ・並びを、モジュールごとに覚える）"] = "",
    closed: Annotated[list[str], "閉じたタブ（作業空間の場所）"] = [],
    vs2026: Annotated[dict, "Visual Studio 2026 で開けるか（ecobuild open --app vs --vs-version 2026 --can：can・reason）"] = {},
    vs2022: Annotated[dict, "Visual Studio 2022 で開けるか（同じ）"] = {},
    vs_version: Annotated[str, "開く Visual Studio の版（作業空間の道具の帯で選んだもの。空なら、この PC に覚えた版・既定 2026）"] = "",
    loading: Annotated[bool, "読み込み中"] = False,
    error: Annotated[str, "読めなかった理由"] = "",
) -> None: ...


def on_selected(
    path: Annotated[str, "出す作業空間の場所"],
    closed: Annotated[list[str], "閉じたままのタブ"] = [],
) -> None:
    if not path:
        raise ValueError("作業空間の場所が要ります")


def on_emptied(closed: Annotated[list[str], "閉じたままのタブ"] = []) -> None: ...


def on_action(
    name: Annotated[str, "操作（explorer：フォルダーを開く・vs：Visual Studio で開く・reload：状態を更新・remove：作業空間を削除・"
                         "task：そのタスクを表示・tasks：タスク管理を開く）"],
    path: Annotated[str, "相手の作業空間の場所"] = "",
    version: Annotated[str, "vs：Visual Studio の版"] = "",
    task: Annotated[int, "task：タスクの番号"] = 0,
) -> None:
    if name not in ("explorer", "vs", "reload", "remove", "task", "tasks"):
        raise ValueError(f"知らない操作です：{name}")
    if name in ("explorer", "vs", "remove") and not path:
        raise ValueError("作業空間の場所が要ります")
