"""gh・git の呼び出し：GitHub・ネットワークの一時的な失敗は、やり直してよい操作だけやり直す。"""

import pytest

from ecotask import process
from ecotask.process import Completed, ProcessFailed


def test_only_repeatable_operations_are_retried():
    assert process.repeatable(["gh", "issue", "view", "22", "--json", "number"])
    assert process.repeatable(["gh", "pr", "list", "--state", "open"])
    assert process.repeatable(["gh", "api", "repos/{owner}/{repo}"])
    assert not process.repeatable(["gh", "api", "--method", "PUT", "repos/x/collaborators/y", "--input", "-"])
    assert not process.repeatable(["gh", "api", "repos/x/issues", "-f", "title=a"])          # -f は POST になる
    assert not process.repeatable(["gh", "issue", "create", "--title", "a"])                 # 作る操作は二重になりうる
    assert process.repeatable(["git", "-c", "core.quotepath=false", "fetch", "--quiet", "--prune", "origin"])
    assert process.repeatable(["git", "push", "origin", "task/1"])
    assert not process.repeatable(["git", "commit", "-m", "x"])


def test_a_transient_failure_is_retried_then_reported(monkeypatch):
    results = iter([Completed(("gh",), 1, "", "HTTP 502: 502 Bad Gateway (https://api.github.com/graphql)"),
                    Completed(("gh",), 0, "{}", "")])
    ran, waited = [], []
    monkeypatch.setattr(process, "_run_once", lambda args, **kw: (ran.append(args), next(results))[1])
    assert process.run(["gh", "issue", "view", "22"], wait=waited.append).ok
    assert len(ran) == 2 and waited == [process.RETRY_WAITS[0]]

    ran.clear(), waited.clear()
    monkeypatch.setattr(process, "_run_once", lambda args, **kw: (ran.append(args),
                                                                   Completed(tuple(args), 1, "", "HTTP 503"))[1])
    with pytest.raises(ProcessFailed):
        process.run(["gh", "issue", "view", "22"], wait=waited.append)
    assert len(ran) == 1 + len(process.RETRY_WAITS)                                         # 決まった回数だけ

    ran.clear()
    with pytest.raises(ProcessFailed):
        process.run(["gh", "issue", "create", "--title", "a"], wait=waited.append)
    assert len(ran) == 1                                                                     # 作る操作はやり直さない

    ran.clear()
    monkeypatch.setattr(process, "_run_once", lambda args, **kw: (ran.append(args),
                                                                   Completed(tuple(args), 1, "", "not found"))[1])
    assert not process.run(["gh", "issue", "view", "99"], check=False, wait=waited.append).ok
    assert len(ran) == 1                                                                     # 一時的でない失敗はそのまま
