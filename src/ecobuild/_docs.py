"""モジュールに置く文書と設定ファイル（README・AGENTS.md・CIのワークフロー）の内容。I-034・機能提案。"""

from __future__ import annotations

from .config import ModuleConfig

CI_WORKFLOW = ".github/workflows/ecobuild.yml"


def readme(config: ModuleConfig) -> str:
    projects = config.projects
    app = f"\n- `{projects.app}`：実行ファイル（`main`だけ）" if projects.app else ""
    return f"""# {config.name}

C++のモジュールです。[ECOBuild](https://github.com/superFUKA/ECOBuild)で管理しています。

## 構成

- `{projects.library}`：ライブラリ（処理の本体）
- `{projects.test}`：テスト（GoogleTest）{app}

## ECOBuildで使う

```sh
ecobuild clone <所有者>/{config.name}   # cloneして依存先も用意する
ecobuild build
ecobuild test
```

作業はIssueごとの作業空間で行います（`ecobuild task new "<題名>" --start` → 編集 → `ecobuild commit` → `ecobuild task submit` → `ecobuild task merge`）。

## ECOBuildなしで使う

CMake 3.24以上とC++20のコンパイラがあれば、cloneしたままビルドできます（依存先は構成時に取得されます）。

```sh
cmake -S . -B build
cmake --build build --config Debug
ctest --test-dir build -C Debug --output-on-failure
```
"""


def agents(config: ModuleConfig) -> str:
    return f"""# AGENTS.md

このリポジトリ（{config.name}）は ECOBuild で管理しています。コーディングエージェントは、gitを直接使わず `ecobuild` コマンドを使ってください。機械で読む場合は各コマンドに `--json` を付けます（標準出力にJSONが1つ、終了コード 0＝成功、1＝失敗、2＝引数の誤り）。

## 作業の流れ

1. `ecobuild task new "<題名>" --body "<内容>" --start`（既存のIssueなら `ecobuild task start <番号>`）
2. 編集する。ファイルの追加は `ecobuild file add <パス>`（ライブラリのソースならテストも作られる）
3. `ecobuild build`・`ecobuild test`（PR前の確認は `ecobuild check`）
4. `ecobuild add --all` → `ecobuild commit --message "<内容>"`
5. `ecobuild task submit`（途中の反映なら `--partial`）→ `ecobuild task merge`
6. `ecobuild task clean`

## 守ること

- コミットは作業空間（`task/<Issue番号>` のブランチ）でだけ行えます。`main` 等へはPRのマージでだけ入ります。
- 取り込み（`ecobuild sync`）で衝突したら、ファイルを直して `ecobuild add` → `ecobuild sync continue`（やめるなら `ecobuild sync abort`）。CppBuildの生成ファイル（`CMakeLists.txt`・`CppBuildTopLevel.cmake`）は直さなくて構いません。
- `.cppbuild/` と生成ファイルは手で編集しません（`ecobuild file`・`ecobuild project`・`ecobuild link` 等で変えます）。
- 失敗したら `error.code` と `error.hint` を読み、案内に従ってください。状態は `ecobuild status --fetch`・`ecobuild task status` で確認できます。
- C++のソースはUTF-8で書きます。
"""


def ci_workflow(config: ModuleConfig) -> str:
    return f"""# ECOBuild（ecobuild ci init）が作成：ECOBuildなしで、CMakeだけで構成・ビルド・テストする。
name: build

on:
  push:
    branches: [{config.default_base}]
  pull_request:

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, ubuntu-latest]
    runs-on: ${{{{ matrix.os }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Configure
        run: cmake -S . -B build
        env:
          # 非公開の依存先を構成時にcloneするため。GITHUB_TOKEN はこのリポジトリしか読めないので、
          # 別の非公開リポジトリに依存するときは、それを読めるトークンを secrets.ECOBUILD_DEPS_TOKEN に登録する。
          GIT_CONFIG_COUNT: 1
          GIT_CONFIG_KEY_0: url.https://x-access-token:${{{{ secrets.ECOBUILD_DEPS_TOKEN || secrets.GITHUB_TOKEN }}}}@github.com/.insteadOf
          GIT_CONFIG_VALUE_0: https://github.com/
      - name: Build
        run: cmake --build build --config Debug
      - name: Test
        run: ctest --test-dir build -C Debug --output-on-failure
"""
