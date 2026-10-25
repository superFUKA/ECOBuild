"""このPCのスキル（手持ちのスキル。モジュールのスキルの元）を扱います。

置き場所は ECOBUILD_HOME/agents/skills/<名前>/ です（コミットしません）。モジュールには
ecobuild agent skill add <名前> --from-preset <このPCのスキル> で写します。モジュールで直したスキルは
ecobuild agent skill preset add <名前> --from-module <スキル> で、Claude Code の個人のスキル等は --from-dir で手持ちにできます。"""
