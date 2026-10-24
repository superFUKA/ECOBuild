"""このPCにあるモジュール（元の clone）と、その中の作業空間を扱います。

作業空間は元の clone の中の .ecobuild/w/<名前>（git worktree）です。task start で作り、task finish・drop・close で
タスクブランチと一緒に消えます（ECOBuild が管理する場所です）。一覧・一覧への追加・一覧から外す・閉じる操作です。"""
