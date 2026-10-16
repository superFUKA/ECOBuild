"""型 python のコマンド（venv・pip・pytest）。CLI（ecobuild_cli）が、型 python のモジュールの中でだけ重ねる。

ここだけは CLI の層：ecobuild_cli の公開の補助（ecobuild_cli.kit）を使ってよい。click・CLIFrameWork は使わない。
型 python の本体（type.py 等）は、ここを import しない。
"""
