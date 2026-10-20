"""CI での見直し（Claude が PR を見直す）のワークフロー。型によらないので本体が作る（ecobuild ci init --review）。

Claude Code の GitHub Action（anthropics/claude-code-action）を、提出（PR）が出た・更新されたときに動かす。作った人とは別の
新しい文脈で、タスク（Issue）の目的・完了の条件と差分を比べ、足りない所・誤りだけを PR のコメントに書く。
見直しは助言：失敗しても取り込みを止めない（承認にも数えない。承認は人がする）。
"""

from __future__ import annotations

from .config import CiSettings

REVIEW_WORKFLOW = ".github/workflows/ecobuild-review.yml"
REVIEW_GUIDE = "REVIEW.md"   # モジュールのルートに置く見直しの観点（任意）
APP_URL = "https://github.com/apps/claude"

# 認証の種類 → （シークレットの名前、Action の入力、作り方）
AUTH = {
    "subscription": ("CLAUDE_CODE_OAUTH_TOKEN", "claude_code_oauth_token",
                     "Claude の契約（Pro・Max・Team・Enterprise）で、このPCの `claude setup-token` で作る"),
    "api-key": ("ANTHROPIC_API_KEY", "anthropic_api_key", "Claude Console（https://platform.claude.com）の API キー"),
}

_TOOLS = ("mcp__github_inline_comment__create_inline_comment", "Bash(gh pr view:*)", "Bash(gh pr diff:*)",
          "Bash(gh pr comment:*)", "Bash(gh issue view:*)", "Read", "Grep", "Glob")

_PROMPT = """\
あなたは PR {repository}#{number} を見直す役です。作った人とは別の目で、足りない所と誤りだけを見つけます。

1. `gh pr view {number}` で PR の本文とコメントを読みます。本文の「Closes #<番号>」か「Refs #<番号>」のタスク（Issue）を
   `gh issue view <番号>` で読みます。Issue の目的・完了の条件が、この PR の基準です（Refs は途中の提出なので、
   完了の条件の一部だけでよい）。
2. `gh pr diff {number}` で差分を読み、必要ならリポジトリのファイルを読みます。
3. リポジトリのルートに REVIEW.md があれば、その観点に従います。AGENTS.md・CLAUDE.md の決まりも基準です。
4. 指摘するのは次のものだけです：
   - 正しさの誤り（バグ・壊れる入力や状態）
   - Issue の完了の条件で、満たしていないもの
   - 確かめ（テスト）が足りない所
   - タスクの範囲の外の変更
   好みの書き方・整形・名前は指摘しません。起きない場合への防御や、余計な抽象化を勧めません。
   以前の見直しで指摘し、直っているものには触れません。直っていないものは繰り返さず、まとめで数えるだけにします。
5. 指摘は根拠のファイルと行を確かめてから、mcp__github_inline_comment__create_inline_comment でその行に書きます
   （何が起きるか・どう直すか）。同じ種類の誤りが何か所にもあれば、1か所に書いてほかの場所を並べます。
6. 最後に、まとめを1つだけ書きます：`gh pr comment {number} --edit-last --create-if-none --body "..."`
   （前の見直しのまとめを書き換える）。先頭は「見直し：指摘 N 件」（なければ「見直し：指摘はありません」）。
   次に、指摘ごとに `ファイル:行` と1行の要約（行のコメントを読まない道具もあるため）。
   最後に、完了の条件ごとに満たしているか（✓／✗／確かめられない）。
7. 本文の「確認（ECOBuild）」は、提出した人の手元での結果です。CI のビルド・テストの結果は別に出ます。

日本語で書きます。この見直しは助言です。承認・差し戻しはしません。
"""


def workflow(ci: CiSettings) -> str:
    secret, field, _ = AUTH[ci.review_auth]
    prompt = _PROMPT.format(repository="${{ github.repository }}", number="${{ github.event.pull_request.number }}")
    lines = [
        "# ECOBuild（ecobuild ci init --review on）が作成：提出（PR）を Claude が見直し、PR のコメントに書く。",
        f"# 要るもの：Claude の GitHub App（{APP_URL}）と、シークレット {secret}（ecobuild ci secret set {secret}）。",
        f"# シークレットがなければ見直しを省く。見直しの観点はモジュールの {REVIEW_GUIDE}（任意）。見直しが失敗しても取り込みは止めない。",
        "name: review", "",
        "on:", "  pull_request:", "    types: [opened, synchronize, ready_for_review, reopened]", "",
        "concurrency:", "  group: ecobuild-review-${{ github.event.pull_request.number }}", "  cancel-in-progress: true", "",
        "jobs:", "  review:", "    if: github.event.pull_request.draft == false", "    runs-on: ubuntu-latest",
        "    timeout-minutes: 30", "    permissions:", "      contents: read", "      pull-requests: write",
        "      issues: read", "      id-token: write", "    steps:",
        "      - id: auth", "        env:", f"          TOKEN: ${{{{ secrets.{secret} }}}}",
        "        run: |", '          if [ -n "$TOKEN" ]; then echo "ready=true" >> "$GITHUB_OUTPUT"',
        f'          else echo "::warning::シークレット {secret} がないため、見直しを省きます（ecobuild ci secret set {secret}）"; fi',
        "      - if: steps.auth.outputs.ready == 'true'", "        uses: actions/checkout@v6", "        with:",
        "          fetch-depth: 1",
        "      - if: steps.auth.outputs.ready == 'true'", "        uses: anthropics/claude-code-action@v1",
        "        continue-on-error: true", "        with:", f"          {field}: ${{{{ secrets.{secret} }}}}",
        "          prompt: |", *[f"            {line}" if line else "" for line in prompt.splitlines()],
        "          claude_args: |", "            --max-turns 40", f'            --allowedTools "{",".join(_TOOLS)}"',
    ]
    return "\n".join(lines) + "\n"
