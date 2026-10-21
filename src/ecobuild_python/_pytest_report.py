"""ecobuild test が pytest に読み込ませるプラグイン（モジュールの .venv の pytest の中で動く。ECOBuild を import しない）。

テストごとの結果（pytest の nodeid・段階・状態・理由・時間）を、環境変数 ECOBUILD_PYTEST_REPORT のファイルへ
1行1件の JSON で書く。pytest-xdist で並べたときは、親（結果が集まる側）だけが書く。
"""

import json
import os

_path = None


def pytest_configure(config):
    global _path
    if not hasattr(config, "workerinput"):   # pytest-xdist のワーカーでは書かない（結果は親に届く）
        _path = os.environ.get("ECOBUILD_PYTEST_REPORT")


def pytest_runtest_logreport(report):
    _write(report, report.when)


def pytest_collectreport(report):
    if report.failed:   # 集める途中の誤り（import の失敗 等）も、そのファイルの失敗として残す
        _write(report, "collect")


def _write(report, when):
    if not _path:
        return
    status = "failed" if report.failed else "skipped" if report.skipped else "passed"
    record = {"nodeid": report.nodeid, "when": when, "status": status, "message": _message(report),
              "duration": getattr(report, "duration", 0.0) or 0.0}
    with open(_path, "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _message(report):
    """失敗：何が起きたか（assert の行・例外）。スキップ：理由。成功：空。"""
    if hasattr(report, "wasxfail"):
        return f"xfail：{report.wasxfail}" if report.wasxfail else "xfail"
    longrepr = report.longrepr
    if report.skipped:
        if isinstance(longrepr, tuple) and len(longrepr) == 3:
            return str(longrepr[2]).removeprefix("Skipped: ")
        return str(longrepr or "")
    if report.failed:
        crash = getattr(longrepr, "reprcrash", None)
        if crash is not None and getattr(crash, "message", ""):
            return crash.message
        text = str(longrepr or "").strip()
        return text.splitlines()[-1] if text else ""
    return ""
