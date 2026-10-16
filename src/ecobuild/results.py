"""ライブラリの戻り値。CLIはこれを人向けの表示とJSONへ変換する。

作業の進め方の戻り値（作業空間・PR・状態等）は ecowork.workspace にある。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Protocol


@dataclass(frozen=True)
class ModuleCreated:
    name: str
    root: Path
    remote_url: str
    projects: tuple[str, ...]


@dataclass(frozen=True)
class ModuleEntry:
    """モジュールの一覧（module list）の1件。GitHubにある、ECOBuildのモジュールのリポジトリ。"""
    repository: str                  # 所有者/名前
    url: str
    type: str                        # モジュールの型（ecobuild.toml に書いたもの。読めなければ空）
    description: str
    private: bool
    archived: bool
    updated: str                     # 最後に更新した日時（ISO 8601）


@dataclass(frozen=True)
class ModuleInfo:
    """今いるモジュールの情報（module show）。"""
    name: str
    type: str
    root: Path
    repository: str                  # 所有者/名前（GitHubのリポジトリでなければ空）
    url: str
    private: bool | None             # GitHubに問い合わせられなければNone
    archived: bool | None
    default_base: str                # 作業空間の既定の作成元
    projects: tuple[str, ...]
    dependencies: tuple[str, ...]    # 直接の依存先の名前
    clones: tuple["CloneEntry", ...] = ()   # このPCにある、このモジュールのclone（記録したもの。ここも含む）


@dataclass(frozen=True)
class CloneEntry:
    """このPCにある、モジュールのclone（module clones）の1件。場所と種類は記録から、他はそのつどcloneから読む。"""
    path: Path
    kind: str                        # module：モジュールのclone、workspace：作業空間専用のclone（task start --dir）
    exists: bool                     # その場所にある（False：移動・削除したか、外付けのドライブを外している）
    repository: str | None = None    # 所有者/名前（origin が GitHub のものなら）
    url: str | None = None           # origin
    branch: str | None = None        # 今のブランチ
    task: int | None = None          # 作業空間（task/<番号>）にいれば、その番号
    remote: str | None = None        # --fetch：ok・archived・moved・gone（GitHubにない）・unknown。GitHubでなければNone
    moved_to: str | None = None      # remote が moved のとき、GitHubでの今の名前


@dataclass(frozen=True)
class CloneForgotten:
    path: Path
    exists: bool                     # フォルダがまだある（中で ecobuild を使うと、また記録される）


@dataclass(frozen=True)
class ModuleArchived:
    repository: str                  # 所有者/名前
    url: str
    archived: bool                   # True：アーカイブした、False：元に戻した


@dataclass(frozen=True)
class ModuleDeleted:
    repository: str                  # 所有者/名前
    url: str
    open_issues: int
    open_pull_requests: int
    task_data: bool                  # タスク管理の情報を閉じた（消さない。リポジトリを戻すと開き直す）
    clone: Path | None = None        # 手元のclone（今いる・今いるディレクトリの <名前>。なければ記録の最初のもの）
    clone_removed: bool = False      # そのcloneも削除した
    clones: tuple[Path, ...] = ()    # このPCにある、このモジュールのcloneすべて（記録したもの・作業空間専用も）
    removed: tuple[Path, ...] = ()   # そのうち削除したもの（--remove-clone。他のプログラムが使っているものは残る）
    done: bool = True                # False：確かめただけ（まだ何も変えていない）


@dataclass(frozen=True)
class DependencyNode:
    """依存関係の図（deps tree）の1件。依存先の依存先も含む。"""
    name: str                        # deps/<名前>
    url: str
    revision: str                    # 記録の版
    present: bool                    # 手元にcloneがある（なければ、その先の依存先は分からない）
    depends_on: tuple[str, ...]      # このモジュールが依存する先（名前）


@dataclass(frozen=True)
class DependencyTree:
    module: str
    direct: tuple[str, ...]          # このモジュールが直接リンクしている依存先
    nodes: tuple[DependencyNode, ...]


@dataclass(frozen=True)
class DependencyChange:
    name: str
    action: str                      # cloned / aligned / unchanged / skipped
    reason: str | None = None


class PrepareResult(NamedTuple):
    """型の prepare（取り込み・切り替えの後に手元をそろえる）の結果。"""
    dependencies: tuple[DependencyChange, ...]   # 依存先の変化
    regenerated: bool                            # 生成ファイルを作り直したか


@dataclass(frozen=True)
class ProjectSummary:
    """Projectの一覧（型の projects）の1件。CLIの表示とJSONはこの形を使う。"""
    name: str
    kind: str                 # 種類（型が決める。cpp：static_library / executable / test 等）
    directory: str            # モジュールからの相対
    links: tuple[str, ...]    # リンクしているProjectと依存先のモジュール
    source_directories: tuple[str, ...] = ()   # ソースフォルダー（Projectからの相対）。ファイルはこの中に置く


class BuildOptions(Protocol):
    """型の build_options が返すビルド設定のうち、本体が読むもの（それ以外は型が決める）。"""
    configuration: str


@dataclass(frozen=True)
class DependencyState:
    name: str
    url: str
    recorded: str                    # 記録された版（コミット）
    local: str | None                # 手元のcloneの版（なければNone）
    state: str                       # aligned / differs / modified / working / missing
    branch: str | None = None        # 作業版ならそのブランチ
    # 以下は deps list --fetch のときだけ（GitHubで、ECOBuildの外で変わったことを見る）
    remote: str | None = None        # ok / archived / moved / gone / unknown
    latest: str | None = None        # GitHubの既定のブランチの最新の版
    moved_to: str | None = None      # remote が moved：新しい 所有者/名前
    via: str | None = None           # 依存先の依存先なら、それを記録している依存先の名前


@dataclass(frozen=True)
class LinkResult:
    name: str                        # 依存先の名前（deps/<名前>）
    url: str
    revision: str
    projects: tuple[str, ...]        # リンクした（外した）Project
    clone_removed: bool = False      # unlink：手元のcloneを消したか（作業中・変更ありなら残す）
    clone: DependencyChange | None = None     # link：手元のcloneを記録の版に合わせた結果（既にcloneがあったとき）


@dataclass(frozen=True)
class CiInitResult:
    path: str
    private_dependencies: tuple[str, ...]   # CIで取得するにはトークンが要る依存先


@dataclass(frozen=True)
class DoctorItem:
    """このPCの診断の1項目（型は doctor_items で、自分が使うツールの分を返す）。"""
    name: str
    ok: bool
    required: bool         # Falseなら、なくても使える（警告だけ）
    detail: str
    hint: str = ""
    fix: str = ""          # 直し方：install／setup-git／identity（setup が直す）、login／scope（init が聞いて直す）
    install: tuple[str, ...] = ()  # fix が install のときの、このOSでの導入コマンド（なければ準備の側の既定）


@dataclass(frozen=True)
class CheckItem:
    name: str                        # generated / conflict_markers / build / test
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class CheckReport:
    items: tuple[CheckItem, ...]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.items)


@dataclass(frozen=True)
class ModuleCloned:
    name: str
    root: Path
    remote_url: str
    projects: tuple[str, ...]
    dependencies: tuple[DependencyChange, ...]


@dataclass(frozen=True)
class SyncResult:
    branch: str
    merged: tuple[str, ...]          # 取り込んだ（または早送りした）参照。sync continueでは merge／rebase
    dependencies: tuple[DependencyChange, ...]
    regenerated: bool


@dataclass(frozen=True)
class BuildResult:
    project: str | None              # Noneは全体
    configuration: str
    artifacts: tuple[str, ...]
    profile: str | None = None       # 使った名前付きビルド設定
    action: str = "build"            # build / clean / rebuild


@dataclass(frozen=True)
class ProfileList:
    profiles: dict                   # 名前 → Profile
    selected: str | None             # このPCで選んでいる設定（ecobuild.local.toml）


@dataclass(frozen=True)
class FilesChanged:
    """ファイル・Projectの操作で変わったファイル（モジュールからの相対パス）。"""
    action: str
    paths: tuple[str, ...]
    project: str | None = None


@dataclass(frozen=True)
class TestCaseResult:
    name: str
    status: str


@dataclass(frozen=True)
class TestResult:
    project: str | None
    configuration: str
    passed: int
    failed: int
    skipped: int
    cases: tuple[TestCaseResult, ...]


@dataclass(frozen=True)
class RunResult:
    project: str | None
    configuration: str
    returncode: int
    output: str
