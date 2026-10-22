"""エージェントの登録（起動できるエージェントの文書・渡すツールの範囲・人が起動できるか・起動してよい子）を扱います。

登録はモジュールではなく、このPCの ECOBuild 全体の設定です。ECOBuild が配る見本（lead・manager・worker）と、
ユーザーの登録（ECOBUILD_HOME/agents/registry/<名前>/）があり、同じ名前ならユーザーの登録を使います。"""
