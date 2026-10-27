"""ecoagent.conversations：Claude Code が記録した会話の一覧（記録は偽の jsonl）。"""

import json
import os
import subprocess
import sys

import ecoagent
from ecoagent import history


def _record(folder, id, lines, mtime):
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / f"{id}.jsonl"
    file.write_text("".join(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n" for line in lines),
                    encoding="utf-8")
    os.utime(file, (mtime, mtime))


def _user(text, branch="task/5", **extra):
    return {"type": "user", "message": {"role": "user", "content": text}, "gitBranch": branch, **extra}


def test_lists_the_conversations_of_the_directory_newest_first(tmp_path):
    projects = tmp_path / "config" / "projects"
    place = tmp_path / "ECO" / "Calc"
    folder = projects / "".join(c if c.isalnum() else "-" for c in str(place))
    _record(folder, "old", [_user("最初の発言です\n2行目"), _user("次")], 1000)
    _record(folder, "named", [_user("x"), {"type": "ai-title", "aiTitle": "AI の名前"},
                              {"type": "custom-title", "customTitle": "付けた名前"}], 3000)
    _record(folder, "ai", [_user([{"type": "text", "text": "y"}], branch="task/6"), {"type": "ai-title", "aiTitle": "AI の名前"}], 2000)
    _record(folder, "empty", [_user("<command-name>/clear</command-name>"), _user("meta", isMeta=True),
                              {"type": "user", "message": {"content": [{"type": "tool_result", "content": "z"}]}}], 4000)
    _record(projects / "other", "elsewhere", [_user("別の場所")], 5000)

    found = ecoagent.conversations(place, config_dir=tmp_path / "config")
    assert [(c.id, c.title, c.prompts, c.branch) for c in found] == [
        ("named", "付けた名前", 1, "task/5"), ("ai", "AI の名前", 1, "task/6"), ("old", "最初の発言です 2行目", 2, "task/5")]
    assert found[0].updated == "1970-01-01T00:50:00+00:00"
    assert [c.id for c in ecoagent.conversations(place, config_dir=tmp_path / "config", branch="task/5", limit=1)] == ["named"]
    assert ecoagent.conversations(tmp_path / "nowhere", config_dir=tmp_path / "config") == []


def test_the_folder_name_differs_only_in_case(tmp_path):
    _record(tmp_path / "projects" / "C--ECO-Calc", "a", [_user("hi")], 1000)
    assert [c.id for c in ecoagent.conversations(r"c:\ECO\Calc", config_dir=tmp_path)] == ["a"]


def test_runs_alone_as_a_script(tmp_path):
    """コンテナの中の Python で、このファイルだけを動かす（結果は JSON）。"""
    _record(tmp_path / "projects" / "-work", "a", [_user("hi", branch="task/1")], 1000)
    _record(tmp_path / "projects" / "-work", "b", [_user("hi", branch="task/2")], 2000)
    done = subprocess.run([sys.executable, "-I", history.__file__, "/work", "task/1"], capture_output=True, text=True,
                          encoding="utf-8", env={**os.environ, "CLAUDE_CONFIG_DIR": str(tmp_path)}, check=True)
    assert [c["id"] for c in json.loads(done.stdout)] == ["a"]


def test_conversations_without_a_known_branch_belong_to_every_branch(tmp_path):
    """ブランチを読めなかった会話（HEAD・空）は、ブランチで絞っても入れる。空の branch は絞らない（中で動かすとき）。"""
    folder = tmp_path / "projects" / "-work"
    _record(folder, "head", [_user("hi", branch="HEAD")], 1000)
    _record(folder, "none", [_user("hi", branch="")], 2000)
    _record(folder, "other", [_user("hi", branch="task/2")], 3000)
    assert [c.id for c in ecoagent.conversations("/work", config_dir=tmp_path, branch="task/1")] == ["none", "head"]
    done = subprocess.run([sys.executable, "-I", history.__file__, "/work", ""], capture_output=True, text=True,
                          encoding="utf-8", env={**os.environ, "CLAUDE_CONFIG_DIR": str(tmp_path)}, check=True)
    assert [c["id"] for c in json.loads(done.stdout)] == ["other", "none", "head"]
