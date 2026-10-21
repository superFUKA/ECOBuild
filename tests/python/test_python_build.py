"""型 python：本物の venv・pip・pytest で、ビルド・テスト・実行（ネットワークが要る。時間がかかる）。"""

import pytest

from fakes import FakeGitHub
from ecobuild.errors import EcoBuildError, ErrorCode
from ecobuild_bundle import Module

pytestmark = pytest.mark.python


def test_build_test_run(tmp_path):
    module = Module.create("Calc", directory=tmp_path, type="python", github=FakeGitHub(tmp_path / "gh"))
    root = module.root
    module.repository.create_task("ビルドする").start()
    assert module.build().artifacts == ()
    stamp = (root / ".venv" / ".ecobuild-stamp").stat().st_mtime_ns
    assert module.build().artifacts == () and (root / ".venv" / ".ecobuild-stamp").stat().st_mtime_ns == stamp
    result = module.test()
    assert result.passed == 1 and result.failed == 0
    assert "Hello from Calc" in module.run().output
    release = module.build(configuration="Release")
    assert sorted(a.rsplit(".", 1)[-1] for a in release.artifacts) == ["gz", "whl"]
    module.build(action="clean")
    assert not (root / "dist").exists() and (root / ".venv").is_dir()

    module.add_file(root / "src/calc/bad.py", test=False)
    (root / "tests" / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    with pytest.raises(EcoBuildError) as error:
        module.test()
    assert error.value.code == ErrorCode.TEST_FAILED and "tests.test_bad::test_bad" in error.value.details["failed"][0]
    selected = module.test(tests=("tests/test_calc.py",))                      # 変えたところのテストだけ（落ちるものは流さない）
    assert selected.passed == 1 and selected.failed == 0
    assert [i.name for i in module.check(build=False).items][:2] == ["generated", "conflict_markers"]


def test_empty_module_builds(tmp_path):
    module = Module.create("Empty", directory=tmp_path, type="python", kind="none", github=FakeGitHub(tmp_path / "gh"))
    module.repository.create_task("空").start()
    module.build()
    assert module.test().passed == 0
