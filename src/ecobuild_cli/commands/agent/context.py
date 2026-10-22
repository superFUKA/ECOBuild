from ecobuild_cli._module import Module


def command() -> int:
    """オペレーターのフック（エージェントの設定から呼ばれます。人が使うものではありません）。

    ユーザーが話しかけるたびに、今の作業空間の一覧（名前・場所・ブランチ）を短く出します。エージェントはそれを発言と
    一緒に受け取るので、場所を調べるコマンドを使わずに、すぐ操作できます。
    """
    try:
        modules = [e for e in Module.workspaces().modules if e.exists]
    except Exception:   # noqa: BLE001 — 文脈を足せないだけ（話しかけるのは止めない）
        return 0
    if not modules:
        return 0
    lines = ["今のモジュールと作業空間（ECOBuild が足した情報。場所はこれを使い、ここで分からないときだけ workspace list）："]
    for e in modules:
        name = e.repository.split("/")[-1] if e.repository else e.path.name
        lines.append(f"- {name}：{e.path}（{_where(e)}{'・' + e.type if e.type else ''}）")
        lines += [f"  - 作業空間 {w.name}：{w.path}（{_where(w)}）" for w in e.workspaces]
    print("\n".join(lines))
    return 0


def _where(e) -> str:
    return (e.branch or "ブランチなし") + (f"＝タスク #{e.task}" if e.task is not None else "")
