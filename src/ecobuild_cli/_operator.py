"""オペレーター（ECOBuild の操作係のエージェント）の指示書と一式。指示書はその時のコマンドの一覧から作る（写しを持たない）。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from ecobuild_agent import operator

from . import _catalog, _effects
from ._module import PROGRAM

MARKS = {_effects.READ: "見る", _effects.CHANGE: "変える", _effects.CONFIRM: "確認", _effects.HUMAN: "人",
         _effects.REQUESTED: "頼まれたら"}

RULES = f"""# ECOBuild オペレーター

あなたは ECOBuild（GitHub のリポジトリ＝モジュールを、Issue＝タスク単位の流れで開発するツール）の **操作係** です。
コードを書く・ファイルを編集するのは仕事ではありません。ユーザーが頼んだ ECOBuild の操作（モジュール・作業空間・タスク・
ブランチ・提出・CI・設定など、ECOBuild の画面でできること）を、`{PROGRAM}` コマンドで実際に行います。

## 読み方

- 言われたことは、まず ECOBuild の操作として読む。対象を言わない頼みは ECOBuild のこと。
- 入力は音声の文字起こしのことがある（誤変換・言い淀み・言い直し・途中で切れた文）。音の近い言葉に読み替えてよい。
- 1回の発言に操作がいくつも入っていることが多い。最初に、全部の「操作×対象」を書き出す。
  「いや」「やっぱ」「じゃなくて」の後ろが正しい（打ち消された対象は外す）。
- 本当にどちらとも読めるときだけ、実行する前に短く聞き返す。分かるところだけやって残りを黙って落とさない。
- 画面に関わる頼み（「〇〇を開いて」「〇〇を見せて」「〇〇出して」「〇〇の開発環境」「前に出して」）は、まず ECOBuild の
  画面の操作（拡張の画面の操作のコマンド。下の一覧の説明と例を見る）として読み、ECOBuild の画面で開くことを第一にする。
  エディター・エクスプローラーなどの外のアプリを開く操作は、そのアプリの名前を言われたときだけ（「VS で」「フォルダを」）。
  そのまま実行し、選択肢の画面（質問のツール）は出さない（声・リングでは答えにくい）。聞き返すときも1行の文で。

## 頼みをコマンドに落とす手順（毎回やる）

1. **全部の操作を書き出す**：発言を「操作（開く・作る・始める・ビルド…）× 対象（モジュール・タスクの番号・タブの番号）」に分ける。
   「と」「それぞれ」「両方」「全部」「〜も」は対象が複数の合図。
2. **言い直しを反映する**：「いや」「やっぱ」「じゃなくて」の後ろが正しい。打ち消された対象は外す。
3. **対象を確かめる**：発言には「今の作業空間」の一覧が付いてくる（名前・場所・ブランチ）。場所はそれを使い、
   そこにないときだけ `{PROGRAM} workspace list --json` で探す。音の近い名前・言い間違いも読み替える
   （「エコ STL」「エコエスティーエル」「SQL」→ ECOSTL）。見つからない・いくつもあるときだけ聞き返す。
   名前を言わないとき（「これ」「今の」「この画面の」）は、ユーザーが今見ている画面のモジュール（今見ているものを
   調べる操作が下の一覧にあれば、それで確かめる）。分からなければ直前に話していたモジュール。
   「さっきの」「あれ」は、直前の会話か一覧から決める。
4. **すぐ実行する**：同じ操作は1回にまとめ、別の操作は続けて実行する。迷って選択肢を出さない（声・リングでは答えにくい）。
5. **全部済んだか照らし合わせる**：1 で書き出した操作が全部成功したかを確かめてから、やったことを全部並べて返す。
   できなかったものがあれば、それも書く。

## 実行のしかた

- `{PROGRAM} … --json` で実行し、結果の `ok`・`error.message`・`error.hint` を読む。
- モジュールの中のコマンドは `{PROGRAM} -C <作業空間の場所> …`。このPCの作業空間は `{PROGRAM} workspace list --json`、
  GitHub にあるモジュールは `{PROGRAM} module list --json`。モジュールの名前で言われたら、そこから場所を探す。
- 使い方は `{PROGRAM} <コマンド> --help --json`。型ごとのコマンド（build・project 等）は
  `{PROGRAM} -C <場所> --help --json` で出る。下の一覧にないことも、まず一覧で探す。
- 対話で聞いてくるコマンドは使えない（答えられない）。必要な値はオプションで渡す。

## 重さ（一覧の [ ] の印）

- [見る]・[変える]：頼まれたらすぐ実行してよい。
- [確認]：消す・取り返しのつかない・ほかの人に届く操作。実行する前に、**実行するコマンドをそのまま**
  （例「`{PROGRAM} -C C:/ECO/Calc task finish 12 --yes` を実行します。よろしいですか？」）示して聞き、
  ユーザーが「はい」と答えたら、そのコマンドを実行する（ECOBuild 自身の確認は --yes で済ませる）。
  `--yes`・`--discard-local`・`--force`・`--remove-workspaces` を付けると、どのコマンドでも [確認] になる。
- [人]：ECOBuild の準備・更新・秘密の値の入力など。使わずに、ユーザーに実行してもらうよう伝える。
- [頼まれたら]：ユーザーが直前の発言でそれを頼んだときだけ（ほかのエージェントへ文字を送る：「〇番に〜と送って」）。
- これはフックでも止めてある。止められたら、回避しようとしない（別のコマンドで同じことをしない）。

## 拡張のコマンド

- `{PROGRAM} --help --json` の extensions にあるもの（画面の操作など）は、`{PROGRAM} <名前> --help --json` で使い方と重さが分かる。
  下の一覧にも、名乗った重さで載せてある。
- ほかのエージェントに文字を送る操作は、ユーザーが「〇番に〜と送って」のように **送ること自体をはっきり頼んだときだけ** 使う。
  依頼文を自分で考えて送らない（受け取ったエージェントは、それを人の指示として実行してしまう）。「〜で始めて」「〜を立ち上げて」は、
  ほとんどがエージェントを開くこと。

## しないこと

- ファイルの作成・編集・移動・削除、コードを書く、調べものをする。頼まれたら「作業空間のエージェントに頼んでください」と返す。
  作業空間がタスクブランチなら `{PROGRAM} -C <場所> agent start` でそこにエージェントを開ける（開くだけ。頼む文は送らない）。
- 使えるのは `{PROGRAM}` と、読むだけのコマンド（ls・cat・grep など）だけ。

## 報告のしかた

- 結果は **1〜3行で短く**。やった操作を全部並べる。前置き・言い直しはいらない。
- 「〜しました」と言ってよいのは、そのコマンドが成功した（`"ok": true`）ときだけ。失敗したら、エラーの内容とヒントを短く伝える。
- 頼まれたことをするコマンドがなければ、実行したふりをせず「それはまだできません」と言う。近いことができるなら添える。
"""


EXAMPLES = (
    ("「ECOSTL 今どうなってる？」「エコ STL の状況は」", f"{PROGRAM} -C <場所> status --json と task status を読み、1〜2行で"),
    ("「ECOSTL のタスク見せて」「やること一覧」", f"{PROGRAM} -C <場所> task list --json（多ければ上から数件を短く）"),
    ("「ECOSTL に、ログを出すってタスク作って」", f"{PROGRAM} -C <場所> task new \"ログを出す\""),
    ("「次やるのどれ？」", f"{PROGRAM} -C <場所> task next --json"),
    ("「12番始めて」「12番に取りかかって」", f"{PROGRAM} -C <場所> task start 12（新しく作るなら --name に短い名前）"),
    ("「ECOSTL ビルドして」「テスト回して」", f"{PROGRAM} -C <場所> build ／ test（結果は成功か、失敗なら原因を1行）"),
    ("「差分見せて」「12番の差分」「直前のコミットの中身」",
     f"{PROGRAM} -C <場所> diff --gui ／ task diff 12 --gui ／ show HEAD --gui（TortoiseGit で開く。tool_missing なら --gui なしで要点を短く）"),
    ("「提出して」「PR 出して」", f"{PROGRAM} -C <場所> task submit（[確認]：コマンドを示して聞いてから）"),
    ("「GitHub にあるモジュールは？」", f"{PROGRAM} module list --json"),
    ("「新しいモジュール作って、名前は Calc」", f"{PROGRAM} module new Calc（型を言われたら --type。言われなければ聞き返す）"),
    ("「設定見せて」", f"{PROGRAM} config list --json"),
)


STYLE_NOTE = "口調・言い回し・呼び方だけを変える。手順・確認・決まり・報告の中身（コマンド・結果・エラー・数字）は変えず、正確に伝える。コミット・PR・コード・文書など、成果物の文には使わない"


def style_section(style: str) -> list[str]:
    """ユーザーが決めた話し方（設定 operator_style・agent_style）。"""
    return ["## 話し方（ユーザーの指定）", "", style.strip(), "", f"（{STYLE_NOTE}）", ""] if style.strip() else []


def instructions(build_cli, effects: dict[str, str] | None = None, summaries: dict[str, str] | None = None,
                 examples: list[tuple[str, str]] | None = None, style: str = "") -> str:
    """指示書：決まり・話し言葉の例・今のコマンドの一覧（重さ付き）。effects・summaries・examples：拡張が名乗ったもの。"""
    catalog = _catalog.catalog(build_cli, {})
    lines = [RULES, *style_section(style), "## 例（言われたこと → すること）", ""]
    for say, do in (*EXAMPLES, *(examples or ())):
        command, _, note = do.partition("（")       # コマンドと注意書きを分ける
        lines.append(f"- {say} → `{command.strip()}`" + (f"（{note}" if note else ""))
    lines += ["", "## コマンド", "", f"共通（どこでも。モジュールの中のものは `-C <場所>` を付ける）：", ""]
    lines += _rows(catalog["commands"])
    for name, entry in catalog["types"].items():
        rows = _rows(entry["commands"])
        if rows:
            lines += ["", f"型 {name} のモジュールだけ（{entry['description']}）：", ""] + rows
    if effects:
        lines += ["", "拡張（名乗った重さ。使い方は `--help --json`）：", ""]
        lines += [f"- `{PROGRAM} {path}` [{MARKS.get(effect, effect)}]" + (f"：{(summaries or {}).get(path)}" if (summaries or {}).get(path) else "")
                  for path, effect in sorted(effects.items())]
    return "\n".join(lines) + "\n"


def _rows(nodes: list[dict]) -> list[str]:
    rows = []
    for node in nodes:
        if node.get("runnable"):
            rows.append(f"- `{PROGRAM} {node['path']}` [{MARKS[node.get('effect', _effects.CHANGE)]}]：{node['summary']}")
        rows += _rows(node.get("commands", []))
    return rows


def prepare(build_cli) -> operator.OperatorKit:
    from . import _extensions
    effects, summaries, examples = {}, {}, []
    for name, path in sorted(_extensions.available().items()):
        found, said = _extensions.help_of(name, path)
        for command, (effect, summary) in found.items():
            effects[command], summaries[command] = effect, summary
        examples += said
    from ecobuild import settings
    style = settings.load_config().get("operator_style", "")
    return operator.prepare(instructions(build_cli, effects, summaries, examples, style), program=PROGRAM, guard=f'"{program_path()}" agent guard',
                            context=f'"{program_path()}" agent context',
                            effects=effects)


def program_path() -> str:
    """フックで呼ぶ ecobuild（このコマンドを動かしているもの。見つからなければ PATH の名前）。"""
    here = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    for candidate in (here, here.with_suffix(".exe")) if here is not None and here.stem.lower() == PROGRAM else ():
        if candidate.is_file():
            return candidate.resolve().as_posix()
    found = shutil.which(PROGRAM)
    return Path(found).as_posix() if found else PROGRAM
