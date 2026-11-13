"""GUI の Python（起動の .pyw も）が、どれも読める（文法の誤りで起動の時点で落ちない）。"""
import ast
from pathlib import Path

GUI = Path(__file__).resolve().parent.parent


def test_every_gui_python_file_parses():
    files = [p for p in [*GUI.glob("*.py"), *GUI.glob("*.pyw"), *(GUI / "eco_gui").rglob("*.py")] if "node_modules" not in p.parts]
    assert any(p.name == "ECOBuildGUINext.pyw" for p in files)
    broken = []
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as error:
            broken.append(f"{path.name}:{error.lineno} {error.msg}")
    assert broken == []
