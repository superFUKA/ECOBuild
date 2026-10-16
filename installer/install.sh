#!/usr/bin/env bash
# ECOBuild のインストーラー（Linux）。
#
#   1. git（と、uv を取ってくる curl）がなければ、パッケージマネージャー（apt-get・dnf・pacman・zypper）で導入する
#      （確認してから。root でなければ sudo を使う）
#   2. uv を導入し（なければ ~/.local/bin に）、ECOBuild を GitHub から導入する（ecobuild コマンドが PATH に入る）。
#      Python 3.11 以上がなければ uv がダウンロードする（sudo 不要。システムの Python は変えない）
#   3. ecobuild init を起動し、質問しながら初期設定を行う
#
# 何度実行してもよい（入っているものは入れ直さず、ECOBuild は指定の版に入れ替える）。
#
# 使い方：bash install.sh [--ref <版>] [--source <ディレクトリ>] [--yes] [--no-init]
#   --ref <版>        導入する ECOBuild の版（ブランチ・タグ・コミット）。既定は環境変数 ECOBUILD_REF、なければ feature/mvp
#   --source <dir>    GitHub ではなく手元のソースから導入する（開発用。ソースの変更がそのまま反映される）
#   --yes             確認せずに進める（ecobuild init も既定の答えで進める。GitHub へのログインは行わない）
#   --no-init         ecobuild init を起動しない
#
# 貼り付けて実行：
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/superFUKA/ECOBuild/feature/mvp/installer/install.sh)"

set -u

REF="${ECOBUILD_REF:-feature/mvp}"
SOURCE=""
YES=0
NO_INIT=0
REPOSITORY="https://github.com/superFUKA/ECOBuild"
UV_INSTALLER="https://astral.sh/uv/install.sh"

step() { printf '\033[36m==> %s\033[0m\n' "$1"; }
done_() { printf '\033[32m    %s\033[0m\n' "$1"; }
fail() { printf '\033[31mエラー：%s\033[0m\n' "$1" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --ref) [ $# -ge 2 ] || fail "--ref に版を指定してください。"; REF="$2"; shift 2 ;;
        --source) [ $# -ge 2 ] || fail "--source にディレクトリを指定してください。"; SOURCE="$2"; shift 2 ;;
        --yes|-y) YES=1; shift ;;
        --no-init) NO_INIT=1; shift ;;
        -h|--help) echo "使い方：bash install.sh [--ref <版>] [--source <ディレクトリ>] [--yes] [--no-init]"; exit 0 ;;
        *) fail "知らないオプションです：$1（--ref・--source・--yes・--no-init）" ;;
    esac
done

has_tty() { (: </dev/tty) 2>/dev/null; }

# 端末から聞く（curl から実行して標準入力がスクリプトでも、端末から読む）。端末がなければ「いいえ」
confirm() {
    [ "$YES" = 1 ] && return 0
    has_tty || return 1
    local answer
    printf '%s [Y/n] ' "$1"
    read -r answer </dev/tty || return 1
    case "$answer" in ""|[yY]*|はい*) return 0 ;; *) return 1 ;; esac
}

package_manager() {
    for manager in apt-get dnf pacman zypper; do
        command -v "$manager" >/dev/null 2>&1 && { echo "$manager"; return 0; }
    done
    return 1
}

# パッケージを導入する（パッケージ名は、ここで使うもの：git・curl はどのディストリビューションでも同じ名前）
install_packages() {
    local manager sudo=""
    manager="$(package_manager)" || fail "$* がありません。パッケージマネージャー（apt-get・dnf・pacman・zypper）が見つからないため、手で導入してから、もう一度実行してください。"
    if [ "$(id -u)" -ne 0 ]; then
        command -v sudo >/dev/null 2>&1 || fail "$* を導入するには root の権限（sudo）が要ります。手で導入してから、もう一度実行してください。"
        sudo="sudo"
    fi
    confirm "$* がありません。$manager で導入しますか？（${sudo:+sudo }$manager）" \
        || fail "$* が必要です。導入してから、もう一度実行してください。"
    case "$manager" in
        apt-get) $sudo apt-get update && $sudo apt-get install --yes "$@" ;;
        dnf) $sudo dnf install --assumeyes "$@" ;;
        pacman) $sudo pacman -S --needed --noconfirm "$@" ;;
        zypper) $sudo zypper --non-interactive install "$@" ;;
    esac || fail "$* の導入に失敗しました（$manager）。"
    done_ "$* を導入しました"
}

[ "$(uname -s)" = "Linux" ] || fail "このインストーラーは Linux 用です（Windows は install.cmd）。"
echo "ECOBuild のインストーラー（版：${SOURCE:-$REF}）"
# uv の既定の置き場所（このシェルでも使えるようにする）
export PATH="${XDG_BIN_HOME:+$XDG_BIN_HOME:}$HOME/.local/bin:$PATH"

# 1. 前提：git（uv が GitHub から取り出すのに使う）と curl（uv を取ってくるのに使う）
step "git を確かめます"
missing=()
command -v git >/dev/null 2>&1 || missing+=(git)
command -v uv >/dev/null 2>&1 || command -v curl >/dev/null 2>&1 || missing+=(curl)
[ ${#missing[@]} -eq 0 ] || install_packages "${missing[@]}"
done_ "git：$(git --version)"

# 2. uv と ECOBuild
step "uv を確かめます"
if ! command -v uv >/dev/null 2>&1; then
    confirm "uv（Python とツールの管理。ECOBuild と、足りなければ Python を入れるのに使う）がありません。~/.local/bin に導入しますか？" \
        || fail "uv が必要です。導入してから、もう一度実行してください（$UV_INSTALLER）。"
    script="$(mktemp)" || fail "一時ファイルを作れません。"
    curl -LsSf "$UV_INSTALLER" -o "$script" || { rm -f "$script"; fail "uv の導入スクリプトを取ってこられません（$UV_INSTALLER）。"; }
    sh "$script" --quiet || { rm -f "$script"; fail "uv の導入に失敗しました。"; }
    rm -f "$script"
    command -v uv >/dev/null 2>&1 || fail "uv を導入しましたが見つかりません。新しい端末を開いて、もう一度実行してください。"
    done_ "uv を導入しました"
fi
done_ "uv：$(uv --version)"

step "ECOBuild を導入します（少し時間がかかります。Python 3.11 以上がなければダウンロードします）"
if [ -n "$SOURCE" ]; then
    uv tool install --reinstall --force --python ">=3.11" --editable "$SOURCE" || fail "ECOBuild の導入に失敗しました。"
else
    uv tool install --reinstall --force --python ">=3.11" "git+$REPOSITORY@$REF" || fail "ECOBuild の導入に失敗しました。"
fi
uv tool update-shell >/dev/null 2>&1 || true   # uv が入れるコマンドの場所を、シェルの起動ファイルの PATH に足す
bin="$(uv tool dir --bin)"
ecobuild="$bin/ecobuild"
[ -x "$ecobuild" ] || fail "ecobuild が見つかりません（$ecobuild）。"
python="$("$(uv tool dir)/ecobuild/bin/python" --version 2>/dev/null)"
done_ "ECOBuild を導入しました：$ecobuild${python:+（$python）}"

# 3. 初期設定
if [ "$NO_INIT" = 0 ]; then
    step "初期設定（ecobuild init）"
    if [ "$YES" = 1 ]; then
        "$ecobuild" init --yes
    elif has_tty; then
        "$ecobuild" init </dev/tty
    else
        "$ecobuild" init
    fi
    [ $? -eq 0 ] || printf '\033[33m初期設定は途中です。あとで ecobuild init を実行すると続きから行えます。\033[0m\n'
fi

echo ""
printf '\033[32m完了しました。新しく開いた端末では、どのディレクトリからでも ecobuild が使えます（ecobuild --help）。\033[0m\n'
echo "更新：もう一度このインストーラーを実行（または uv tool upgrade ecobuild）。削除：uv tool uninstall ecobuild"
