"""作業空間をコンテナにします（Docker が要ります）。

このPCの、今いる作業空間だけが対象です（Docker は ecobuild setup --docker で導入できます）。ファイルは今の場所に
置いたまま、コンテナにはこの作業空間に要るものだけを見せます：元の clone の中の作業空間（.ecobuild/w/<名前>）は、
元の .git と自分の作業空間を、このPCと同じ並びで /repo の下に（/repo/.git・/repo/.ecobuild/w/<名前>。元の clone の
作業ツリー・ほかの作業空間は見せません）。前の版の作業空間（独立した clone）は、そのフォルダを /work に。
選択はこのPCの ecobuild.local.toml に書きます（コミットしません）。コンテナにした作業空間では、ビルド・テスト等とエージェントがコンテナの中で動きます。
イメージはモジュールの .ecobuild/container/Dockerfile（環境。コミットしてほかの端末と共有）に
ECOBuild を重ねて作ります。一覧・作成・片付けは container image で扱います。"""
