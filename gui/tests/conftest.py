"""gui の試験の共通の用意。"""

import pytest


@pytest.fixture(autouse=True)
def _one_gui(monkeypatch):
    """GUI の操作の頼み先を、今までの GUI に決めておく（ecobuild_gui.target）。

    決めないと、動いている GUI を調べに行く（このPCで動いている新しい GUI・その中継地点に、試験が触ってしまう）。
    新しい GUI への道の試験は、自分で next にする。
    """
    monkeypatch.setenv("ECOBUILD_GUI_TARGET", "classic")
    for name in ("GUIFRAMEWORK_WINDOW", "GUIFRAMEWORK_RUN", "GUIFRAMEWORK_REQUESTER", "ECOBUILD_GUI_NEXT_PYTHON"):
        monkeypatch.delenv(name, raising=False)
