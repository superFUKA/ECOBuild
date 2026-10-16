"""型 cpp のコマンド（C++。CppBuild）。CLI（ecobuild_cli）が、型 cpp のモジュールの中でだけ重ねる。

ここだけは CLI の層：ecobuild_cli の公開の補助（ecobuild_cli.kit）を使ってよい。click・CLIFrameWork は使わない。
型 cpp の本体（type.py 等）は、ここを import しない。
"""
