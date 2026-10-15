"""管理するファイルのパターン（.gitignore と同じ考え方）と、ecobuild.toml の [files]。"""

import pytest

from ecobuild import tracking
from ecobuild.errors import EcoBuildError


@pytest.mark.parametrize("pattern, path, expected", [
    ("*.cpp", "a.cpp", True),
    ("*.cpp", "src/deep/a.cpp", True),           # / を含まなければ、どの階層の名前にも当たる
    ("*.cpp", "a.cpp.bak", False),
    ("*.h", "include/Lib/a.hpp", False),
    ("/README.md", "README.md", True),           # / を含めばルートからの相対
    ("/README.md", "docs/README.md", False),
    ("docs/*.md", "docs/a.md", True),
    ("docs/*.md", "docs/sub/a.md", False),
    ("docs/**", "docs/sub/a.md", True),
    ("data/", "data/x/y.json", True),             # 末尾の / はそのフォルダーの中すべて
    ("**/test_*.py", "test_a.py", True),
    ("**/test_*.py", "pkg/test_a.py", True),
    ("a?.txt", "ab.txt", True),
    ("a?.txt", "a/.txt", False),
    (".github/workflows/*.yml", ".github/workflows/ci.yml", True),
])
def test_matches(pattern, path, expected):
    assert tracking.matches(pattern, path) is expected


def test_lists_round_trip():
    extra = tracking.with_lists({"ci": {"shared": False}}, ("*.json",), ("*.md",))
    assert extra == {"ci": {"shared": False}, "files": {"include": ["*.json"], "exclude": ["*.md"]}}
    assert tracking.module_lists(extra) == (("*.json",), ("*.md",))
    assert tracking.with_lists(extra, (), ()) == {"ci": {"shared": False}}
    with pytest.raises(EcoBuildError):
        tracking.module_lists({"files": {"include": "*.json"}})
