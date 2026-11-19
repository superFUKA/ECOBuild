"""窓の見た目の組み立て（create_app に渡すもの）。app.py と試験が使う。

窓の枠・重ねた箱の枠・並べる部品（row・column・tabs・split）・メニュー（lib.menu）は、GUIFrameWork の見本 guiframework_basic。
見た目は eco_gui の theme.css を上に重ねる。確認だけは自分の部品（初めのフォーカスが「いいえ」）。
"""

import guiframework_basic

LOOK = {"extensions": {"": guiframework_basic}, "roles": {**guiframework_basic.ROLES, "confirm": "confirm-box"}}
