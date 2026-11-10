"""組み立て。バックエンドは `ecobuild -C <モジュールのフォルダー>`。

    python -m eco_gui.app serve --screen overview     # gui/ のフォルダーで。中継地点を起こし、モジュールの窓を開く
    python -m eco_gui.app tree                        # 別の端末から：今の表示を読む

モジュールのフォルダーは環境変数 ECOBUILD_GUI_MODULE（なければ今のフォルダー）。
ecobuild の場所は環境変数 ECOBUILD_GUI_ECOBUILD（なければ PATH の ecobuild）。
"""

import os
import shutil

from guiframework import create_app

import eco_gui
from eco_gui.backend import EcobuildBackend


def backend() -> EcobuildBackend:
    ecobuild = os.environ.get("ECOBUILD_GUI_ECOBUILD") or shutil.which("ecobuild") or "ecobuild"
    module = os.environ.get("ECOBUILD_GUI_MODULE") or os.getcwd()
    return EcobuildBackend([ecobuild, "-C", module])


app = create_app(eco_gui, name="ecobuild-gui-next", backend=backend(), roles={"confirm": "confirm-box"})
cli = app.cli

if __name__ == "__main__":
    cli()
