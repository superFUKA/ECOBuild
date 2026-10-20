"""作業空間をコンテナにします（Docker が要ります）。

このPCの、今いる作業空間だけが対象です（Docker は ecobuild setup --docker で導入できます）。ファイルは今の場所に
置いたまま、コンテナにはこの作業空間のフォルダだけを /work として見せます。選択はこのPCの ecobuild.local.toml に
書きます（コミットしません）。コンテナにした作業空間では、ビルド・テスト等とエージェントがコンテナの中で動きます。
イメージはモジュールの .ecobuild/container/Dockerfile（環境。コミットしてほかの端末と共有）に
ECOBuild を重ねて作ります。一覧・作成・片付けは container image で扱います。"""
