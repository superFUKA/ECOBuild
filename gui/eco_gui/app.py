"""組み立て。バックエンドは `ecobuild -C <モジュールのフォルダー>`。

    python -m eco_gui.app serve --screen members      # gui/ のフォルダーで。中継地点を起こし、画面を開く
    python -m eco_gui.app tree                        # 別の端末から：今の表示を読む

モジュールのフォルダーは環境変数 ECOBUILD_GUI_MODULE（なければ今のフォルダー）。
ecobuild の場所は環境変数 ECOBUILD_GUI_ECOBUILD（なければ PATH の ecobuild）。
"""

import os
import shutil

from guiframework import create_app
from guiframework.backend import MachineBackend

import eco_gui


def backend() -> MachineBackend:
    ecobuild = os.environ.get("ECOBUILD_GUI_ECOBUILD") or shutil.which("ecobuild") or "ecobuild"
    module = os.environ.get("ECOBUILD_GUI_MODULE") or os.getcwd()
    # 「人がする」（human）の重さのコマンドは、窓の前の人に確かめてから実行する
    return MachineBackend([ecobuild, "-C", module], effects={"human": "confirm"})


app = create_app(eco_gui, name="ecobuild-gui-next", backend=backend(), roles={"confirm": "confirm-box"})
cli = app.cli

if __name__ == "__main__":
    cli()
