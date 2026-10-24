"""エージェントのプリセット（このPCの手持ちのエージェント。モジュールの登録の元）を扱います。

プリセットは、ECOBuild が配る見本（lead・manager・worker）と、このPCのプリセット（ECOBUILD_HOME/agents/presets/<名前>/。
コミットしません）です。モジュールには ecobuild agent registry add <名前> --from-preset <プリセット> で写して登録します。
モジュールで直した登録は ecobuild agent preset add <名前> --from-module <登録> で手持ちにできます。"""
