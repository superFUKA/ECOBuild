"""組み立て。バックエンドは `ecobuild`。どのモジュールで実行するかは、画面の引数 module で決まる。

    python -m eco_gui.app serve --screen hub                 # gui/ のフォルダーで。中継地点を起こし、ハブを開く
    python -m eco_gui.app open overview module=C:\\path\\to\\module   # 別の端末から：モジュールの窓を開く
    python -m eco_gui.app tree                               # 今の表示を読む

ecobuild の場所は環境変数 ECOBUILD_GUI_ECOBUILD（なければ PATH の ecobuild）。
"""

import os
import shutil

from guiframework import create_app

import eco_gui
from eco_gui.backend import EcobuildBackend
from eco_gui.look import LOOK
from eco_gui.shell import open_window


def backend() -> EcobuildBackend:
    ecobuild = os.environ.get("ECOBUILD_GUI_ECOBUILD") or shutil.which("ecobuild") or "ecobuild"
    return EcobuildBackend([ecobuild])


app = create_app(eco_gui, name="ecobuild-gui-next", backend=backend(), opener=open_window, **LOOK)  # 見た目は look.py
cli = app.cli

if __name__ == "__main__":
    cli()
