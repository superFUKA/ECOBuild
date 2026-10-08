"""GitHub の呼び出し（タスク管理の分）。本物は gh を使う。試験では同じメソッドを持つ偽物に差し替える。

Issue・ラベル・コメント・親子（Sub-issues）・依存（Issue dependencies）・マイルストーン・ボード（Projects）。
gh に専用のコマンドがないもの・gh の版で壊れやすいもの（Projects）は gh api（REST・GraphQL）を使う。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import _process
from . import board as _board
from .errors import ErrorCode, TaskError


@dataclass(frozen=True)
class IssueInfo:
    number: int
    title: str
    url: str
    state: str            # open / closed
    body: str = ""
    labels: tuple[str, ...] = ()
    assignees: tuple[str, ...] = ()     # ログイン名
    milestone: str | None = None        # マイルストーンの題名


@dataclass(frozen=True)
class IssueRelations:
    """Issueの親子・依存の要約（一覧1回で取れる分）。"""
    parent: int | None = None           # 親のIssue
    sub_total: int = 0                  # 子のIssueの数
    sub_completed: int = 0              # そのうち閉じたもの
    blocked_by: int = 0                 # 先に終わるべきIssueのうち、開いているものの数
    blocking: int = 0                   # このIssueを待っているIssueのうち、開いているものの数


@dataclass(frozen=True)
class TaskRecord:
    """保存の層が読む、タスク1件分のGitHubのデータ（Issue・親子と依存の要約・マイルストーン・ボードの値）。"""
    issue: IssueInfo
    relations: IssueRelations
    closed_reason: str | None = None    # completed / not_planned
    milestone_due: str | None = None    # YYYY-MM-DD
    item: "_board.BoardItem | None" = None


@dataclass(frozen=True)
class MilestoneInfo:
    number: int
    title: str
    state: str            # open / closed
    url: str
    due: str | None = None              # 期日（YYYY-MM-DD）
    description: str = ""
    open_issues: int = 0
    closed_issues: int = 0


@dataclass(frozen=True)
class Comment:
    author: str
    body: str


class TaskGitHub(Protocol):
    def create_issue(self, repo: Path, title: str, body: str, *, labels: tuple[str, ...] = (),
                     assignees: tuple[str, ...] = ()) -> IssueInfo: ...
    def get_issue(self, repo: Path, number: int) -> IssueInfo: ...
    def list_issues(self, repo: Path, *, closed: bool, label: str | None = None, assignee: str | None = None,
                    search: str | None = None) -> list[IssueInfo]: ...
    def edit_issue(self, repo: Path, number: int, *, title: str | None = None, body: str | None = None,
                   add_labels: tuple[str, ...] = (), remove_labels: tuple[str, ...] = (),
                   add_assignees: tuple[str, ...] = (), remove_assignees: tuple[str, ...] = ()) -> None: ...
    def comment_issue(self, repo: Path, number: int, body: str) -> None: ...
    def issue_comments(self, repo: Path, number: int) -> list[Comment]: ...
    def reopen_issue(self, repo: Path, number: int) -> None: ...
    def close_issue(self, repo: Path, number: int, *, not_planned: bool = False) -> None: ...
    # 親子（Sub-issues）・依存（Issue dependencies）・マイルストーン
    def issue_relations(self, repo: Path, *, closed: bool) -> dict[int, IssueRelations]: ...
    def issue_relation(self, repo: Path, number: int) -> IssueRelations: ...
    def sub_issues(self, repo: Path, number: int) -> list[IssueInfo]: ...
    def add_sub_issue(self, repo: Path, parent: int, child: int) -> None: ...
    def remove_sub_issue(self, repo: Path, parent: int, child: int) -> None: ...
    def blocked_by(self, repo: Path, number: int) -> list[IssueInfo]: ...
    def blocking(self, repo: Path, number: int) -> list[IssueInfo]: ...
    def add_blocked_by(self, repo: Path, number: int, blocker: int) -> None: ...
    def remove_blocked_by(self, repo: Path, number: int, blocker: int) -> None: ...
    def list_milestones(self, repo: Path, *, closed: bool) -> list[MilestoneInfo]: ...
    def create_milestone(self, repo: Path, title: str, *, due: str | None, description: str) -> MilestoneInfo: ...
    def edit_milestone(self, repo: Path, number: int, *, title: str | None = None, due: str | None = None,
                       description: str | None = None, state: str | None = None) -> MilestoneInfo: ...
    def set_issue_milestone(self, repo: Path, number: int, milestone: int | None) -> None: ...
    # ボード（GitHub Projects。ghのトークンに project の権限が必要）
    def list_boards(self, repo: Path, owner: str | None) -> list[_board.BoardInfo]: ...
    def get_board(self, repo: Path, owner: str, number: int) -> _board.BoardInfo: ...
    def link_board(self, repo: Path, board_id: str, *, link: bool) -> None: ...
    def create_board(self, repo: Path, owner: str | None, title: str) -> _board.BoardInfo: ...
    def set_board_options(self, repo: Path, field_id: str, options: tuple[tuple[str, str, str], ...]) -> None: ...
    def create_board_field(self, repo: Path, board_id: str, name: str, type: str, *,
                           options: tuple[tuple[str, str, str], ...] = (),
                           iterations: tuple[tuple[str, str, int], ...] = ()) -> None: ...
    def board_items(self, repo: Path, board_id: str, *, closed: bool) -> dict[int, _board.BoardItem]: ...
    def task_records(self, repo: Path, *, closed: bool, board_id: str | None,
                     number: int | None = None) -> list[TaskRecord]: ...
    def board_item(self, repo: Path, number: int, board_id: str) -> _board.BoardItem | None: ...
    def add_board_item(self, repo: Path, number: int, board_id: str) -> _board.BoardItem: ...
    def set_board_value(self, repo: Path, board_id: str, item_id: str, field: _board.BoardField, value: str) -> None: ...
    def clear_board_value(self, repo: Path, board_id: str, item_id: str, field_id: str) -> None: ...


class GhCli:
    """gh コマンドによる実装。repoは手元のcloneのパス（originからリポジトリを決める）。"""

    def create_issue(self, repo, title, body, *, labels=(), assignees=()):
        self._ensure_labels(repo, labels)
        args = ["issue", "create", "--title", title, "--body", body]
        for label in labels:
            args += ["--label", label]
        for assignee in assignees:
            args += ["--assignee", assignee]
        url = self._gh(args, cwd=repo).stdout.strip()
        return self.get_issue(repo, _number_from_url(url))

    def get_issue(self, repo, number):
        completed = self._gh(["issue", "view", str(number), "--json", _ISSUE_FIELDS],
                             cwd=repo, check=False)
        if not completed.ok:
            if not _not_found(completed):
                raise _gh_error(["issue", "view"], completed)
            raise TaskError(ErrorCode.TASK_NOT_FOUND, f"Issue #{number} が見つかりません。",
                                details=completed.output)
        return _issue(json.loads(completed.stdout))

    def close_issue(self, repo, number, *, not_planned=False):
        reason = "not planned" if not_planned else "completed"
        self._gh(["issue", "close", str(number), "--reason", reason], cwd=repo)

    def list_issues(self, repo, *, closed, label=None, assignee=None, search=None):
        args = ["issue", "list", "--state", "all" if closed else "open", "--limit", "200", "--json", _ISSUE_FIELDS]
        for option, value in (("--label", label), ("--assignee", assignee), ("--search", search)):
            if value:
                args += [option, value]
        return [_issue(d) for d in self._json(args, cwd=repo)]

    def edit_issue(self, repo, number, *, title=None, body=None, add_labels=(), remove_labels=(),
                   add_assignees=(), remove_assignees=()):
        self._ensure_labels(repo, add_labels)
        args = ["issue", "edit", str(number)]
        if title is not None:
            args += ["--title", title]
        if body is not None:
            args += ["--body", body]
        for option, values in (("--add-label", add_labels), ("--remove-label", remove_labels),
                               ("--add-assignee", add_assignees), ("--remove-assignee", remove_assignees)):
            for value in values:
                args += [option, value]
        self._gh(args, cwd=repo)

    def comment_issue(self, repo, number, body):
        self._gh(["issue", "comment", str(number), "--body", body], cwd=repo)

    def issue_comments(self, repo, number):
        data = self._json(["issue", "view", str(number), "--json", "comments"], cwd=repo)
        return [Comment((c.get("author") or {}).get("login", ""), c.get("body") or "") for c in data.get("comments") or []]

    def _ensure_labels(self, repo, labels):
        """ラベルはリポジトリにないと付けられないため、なければ作る。"""
        if not labels:
            return
        existing = {d["name"] for d in self._json(["label", "list", "--limit", "500", "--json", "name"], cwd=repo)}
        for label in labels:
            if label not in existing:
                self._gh(["label", "create", label], cwd=repo)

    def reopen_issue(self, repo, number):
        self._gh(["issue", "reopen", str(number)], cwd=repo)

    def _api(self, method, path, payload, *, cwd):
        """REST API（repos/<所有者>/<名前>/<path>）を呼ぶ。payload はJSONで標準入力から渡す。"""
        args = ["api", "--method", method, f"repos/{{owner}}/{{repo}}/{path}"]
        if payload is not None:
            args += ["--input", "-"]
        try:
            completed = _process.run(["gh", *args], cwd=cwd, input=None if payload is None else json.dumps(payload),
                                     env={"GH_PROMPT_DISABLED": "1"})
        except _process.ProcessFailed as failure:
            raise _api_error(failure.completed) from None
        return json.loads(completed.stdout) if completed.stdout.strip() else None

    def issue_relations(self, repo, *, closed):
        query = (".[] | select(.pull_request == null) | {number, parent: .parent_issue_url, "
                 "sub: .sub_issues_summary, dep: .issue_dependencies_summary}")
        state = "all" if closed else "open"
        output = self._gh(["api", "--paginate", f"repos/{{owner}}/{{repo}}/issues?state={state}&per_page=100",
                           "--jq", query], cwd=repo).stdout
        result = {}
        for line in output.splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            sub, dep = d.get("sub") or {}, d.get("dep") or {}
            result[d["number"]] = IssueRelations(
                _number_from_url(d["parent"]) if d.get("parent") else None, sub.get("total", 0),
                sub.get("completed", 0), dep.get("blocked_by", 0), dep.get("blocking", 0))
        return result

    def issue_relation(self, repo, number):
        d = self._json(["api", f"repos/{{owner}}/{{repo}}/issues/{number}", "--jq",
                        "{parent: .parent_issue_url, sub: .sub_issues_summary, dep: .issue_dependencies_summary}"],
                       cwd=repo)
        sub, dep = d.get("sub") or {}, d.get("dep") or {}
        return IssueRelations(_number_from_url(d["parent"]) if d.get("parent") else None, sub.get("total", 0),
                              sub.get("completed", 0), dep.get("blocked_by", 0), dep.get("blocking", 0))

    def sub_issues(self, repo, number):
        return self._rest_issues(repo, f"issues/{number}/sub_issues")

    def add_sub_issue(self, repo, parent, child):
        self._api("POST", f"issues/{parent}/sub_issues", {"sub_issue_id": self._issue_id(repo, child)}, cwd=repo)

    def remove_sub_issue(self, repo, parent, child):
        self._api("DELETE", f"issues/{parent}/sub_issue", {"sub_issue_id": self._issue_id(repo, child)}, cwd=repo)

    def blocked_by(self, repo, number):
        return self._rest_issues(repo, f"issues/{number}/dependencies/blocked_by")

    def blocking(self, repo, number):
        return self._rest_issues(repo, f"issues/{number}/dependencies/blocking")

    def add_blocked_by(self, repo, number, blocker):
        self._api("POST", f"issues/{number}/dependencies/blocked_by", {"issue_id": self._issue_id(repo, blocker)},
                  cwd=repo)

    def remove_blocked_by(self, repo, number, blocker):
        self._api("DELETE", f"issues/{number}/dependencies/blocked_by/{self._issue_id(repo, blocker)}", None, cwd=repo)

    def list_milestones(self, repo, *, closed):
        state = "all" if closed else "open"
        output = self._gh(["api", "--paginate", f"repos/{{owner}}/{{repo}}/milestones?state={state}&per_page=100"
                           "&sort=due_on", "--jq", ".[]"], cwd=repo).stdout
        return [_milestone(json.loads(line)) for line in output.splitlines() if line.strip()]

    def create_milestone(self, repo, title, *, due, description):
        payload = {"title": title, "description": description}
        if due:
            payload["due_on"] = _due_on(due)
        return _milestone(self._api("POST", "milestones", payload, cwd=repo))

    def edit_milestone(self, repo, number, *, title=None, due=None, description=None, state=None):
        payload = {key: value for key, value in (("title", title), ("description", description), ("state", state))
                   if value is not None}
        if due is not None:
            payload["due_on"] = _due_on(due) if due else None
        return _milestone(self._api("PATCH", f"milestones/{number}", payload, cwd=repo))

    def set_issue_milestone(self, repo, number, milestone):
        self._api("PATCH", f"issues/{number}", {"milestone": milestone}, cwd=repo)

    def list_boards(self, repo, owner):
        owner = owner or self._repo_name(repo)[0]
        data = self._graphql(repo, """
            query($login: String!) { repositoryOwner(login: $login) { ... on ProjectV2Owner {
              projectsV2(first: 100) { nodes { id number title url closed } } } } }""", login=owner)
        owner_data = data.get("repositoryOwner")
        if owner_data is None:
            raise TaskError(ErrorCode.REPOSITORY_NOT_FOUND, f"GitHubに所有者 {owner} が見つかりません。")
        return [_board.BoardInfo(n["id"], n["number"], n["title"], n["url"], (), n["closed"])
                for n in owner_data["projectsV2"]["nodes"]]

    def get_board(self, repo, owner, number):
        data = self._graphql(repo, """
            query($login: String!, $number: Int!) { repositoryOwner(login: $login) { ... on ProjectV2Owner {
              projectV2(number: $number) { id number title url closed fields(first: 100) { nodes {
                ... on ProjectV2Field { id name dataType }
                ... on ProjectV2SingleSelectField { id name dataType options { id name } }
                ... on ProjectV2IterationField { id name dataType
                    configuration { iterations { id title startDate duration }
                                    completedIterations { id title startDate duration } } } } } } } } }""",
                             login=owner, number=number)
        project = (data.get("repositoryOwner") or {}).get("projectV2")
        if project is None:
            raise TaskError(ErrorCode.NO_BOARD, f"ボード {owner} の {number} 番が見つかりません。",
                            hint="URLと、そのボードを見られるアカウントか確かめてください。")
        fields = []
        for node in project["fields"]["nodes"]:
            if not node:
                continue
            options = [_board.BoardOption(o["id"], o["name"]) for o in node.get("options") or []]
            configuration = node.get("configuration") or {}
            iterations = (configuration.get("iterations") or []) + (configuration.get("completedIterations") or [])
            options += [_board.BoardOption(i["id"], i["title"], i.get("startDate"), i.get("duration"))
                        for i in sorted(iterations, key=lambda i: i.get("startDate") or "")]
            fields.append(_board.BoardField(node["id"], node["name"], node["dataType"], tuple(options)))
        return _board.BoardInfo(project["id"], project["number"], project["title"], project["url"], tuple(fields),
                                project["closed"])

    def create_board(self, repo, owner, title):
        owner = owner or self._repo_name(repo)[0]
        owner_id = self._graphql(repo, "query($login: String!) { repositoryOwner(login: $login) { id } }",
                                 login=owner)["repositoryOwner"]["id"]
        project = self._graphql(repo, """
            mutation($owner: ID!, $title: String!) {
              createProjectV2(input: {ownerId: $owner, title: $title}) { projectV2 { id number title url closed } } }""",
                                owner=owner_id, title=title)["createProjectV2"]["projectV2"]
        return _board.BoardInfo(project["id"], project["number"], project["title"], project["url"], (),
                                project["closed"])

    def set_board_options(self, repo, field_id, options):
        """単一選択の選択肢を置き換える（GitHubの仕様で、既存の値は消える）。options：（名前, 色, 説明）。"""
        self._graphql(repo, """
            mutation($field: ID!, $options: [ProjectV2SingleSelectFieldOptionInput!]) {
              updateProjectV2Field(input: {fieldId: $field, singleSelectOptions: $options}) { projectV2Field {
                ... on ProjectV2SingleSelectField { id } } } }""",
                      field=field_id, options=[{"name": n, "color": c, "description": d} for n, c, d in options])

    def create_board_field(self, repo, board_id, name, type, *, options=(), iterations=()):
        """フィールドを足す。options：単一選択の（名前, 色, 説明）、iterations：イテレーションの（題名, 始まり, 日数）。"""
        variables = {"project": board_id, "name": name, "type": type}
        extra = ""
        if options:
            variables["options"] = [{"name": n, "color": c, "description": d} for n, c, d in options]
            extra += ", singleSelectOptions: $options"
        if iterations:
            variables["iterations"] = {"startDate": iterations[0][1], "duration": iterations[0][2],
                                       "iterations": [{"title": t, "startDate": s, "duration": d}
                                                      for t, s, d in iterations]}
            extra += ", iterationConfiguration: $iterations"
        declared = "".join([", $options: [ProjectV2SingleSelectFieldOptionInput!]" if options else "",
                            ", $iterations: ProjectV2IterationFieldConfigurationInput" if iterations else ""])
        self._graphql(repo, f"""
            mutation($project: ID!, $name: String!, $type: ProjectV2CustomFieldType!{declared}) {{
              createProjectV2Field(input: {{projectId: $project, dataType: $type, name: $name{extra}}}) {{
                projectV2Field {{ ... on ProjectV2FieldCommon {{ id }} }} }} }}""", **variables)

    def link_board(self, repo, board_id, *, link):
        repository_id = self._graphql(repo, """
            query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { id } }""",
                                      **self._repo_vars(repo))["repository"]["id"]
        mutation = "linkProjectV2ToRepository" if link else "unlinkProjectV2FromRepository"
        self._graphql(repo, f"""
            mutation($project: ID!, $repository: ID!) {{
              {mutation}(input: {{projectId: $project, repositoryId: $repository}}) {{ repository {{ id }} }} }}""",
                      project=board_id, repository=repository_id)

    def task_records(self, repo, *, closed, board_id, number=None):
        """タスクをまとめて読む（GraphQL：1ページ50件ごとに1回）。number を指定するとその1件だけ。"""
        items = (" projectItems(first: 20) { nodes { id project { id } " + _VALUES + " } }") if board_id else ""
        fields = ("number title url state stateReason body parent { number } subIssuesSummary { total completed } "
                  "issueDependenciesSummary { blockedBy blocking } milestone { title dueOn } "
                  "assignees(first: 20) { nodes { login } } labels(first: 50) { nodes { name } }" + items)
        if number is not None:
            data = self._graphql(repo, """
                query($owner: String!, $name: String!, $number: Int!) { repository(owner: $owner, name: $name) {
                  issue(number: $number) { """ + fields + " } } }", number=number, **self._repo_vars(repo))
            node = data["repository"]["issue"]
            if node is None:
                raise TaskError(ErrorCode.TASK_NOT_FOUND, f"Issue #{number} が見つかりません。")
            return [_task_record(node, board_id)]
        records, after = [], None
        while True:
            data = self._graphql(repo, """
                query($owner: String!, $name: String!, $states: [IssueState!], $after: String) {
                  repository(owner: $owner, name: $name) { issues(first: 50, after: $after, states: $states) {
                    pageInfo { hasNextPage endCursor } nodes { """ + fields + " } } } }",
                                 states=None if closed else ["OPEN"], after=after, **self._repo_vars(repo))
            issues = data["repository"]["issues"]
            records += [_task_record(node, board_id) for node in issues["nodes"]]
            if not issues["pageInfo"]["hasNextPage"]:
                return records
            after = issues["pageInfo"]["endCursor"]

    def board_items(self, repo, board_id, *, closed):
        result, after = {}, None
        while True:
            data = self._graphql(repo, """
                query($owner: String!, $name: String!, $states: [IssueState!], $after: String) {
                  repository(owner: $owner, name: $name) { issues(first: 50, after: $after, states: $states) {
                    pageInfo { hasNextPage endCursor }
                    nodes { number projectItems(first: 20) { nodes { id project { id } """ + _VALUES + """ } } } } } }""",
                                 states=None if closed else ["OPEN"], after=after, **self._repo_vars(repo))
            issues = data["repository"]["issues"]
            for node in issues["nodes"]:
                item = _board_item(node["projectItems"]["nodes"], board_id)
                if item is not None:
                    result[node["number"]] = item
            if not issues["pageInfo"]["hasNextPage"]:
                return result
            after = issues["pageInfo"]["endCursor"]

    def board_item(self, repo, number, board_id):
        return _board_item(self._issue_items(repo, number)["projectItems"]["nodes"], board_id)

    def add_board_item(self, repo, number, board_id):
        issue = self._issue_items(repo, number)
        item = _board_item(issue["projectItems"]["nodes"], board_id)
        if item is not None:
            return item
        data = self._graphql(repo, """
            mutation($project: ID!, $content: ID!) {
              addProjectV2ItemById(input: {projectId: $project, contentId: $content}) { item { id } } }""",
                             project=board_id, content=issue["id"])
        return _board.BoardItem(data["addProjectV2ItemById"]["item"]["id"], {})

    def set_board_value(self, repo, board_id, item_id, field, value):
        self._graphql(repo, """
            mutation($project: ID!, $item: ID!, $field: ID!, $value: ProjectV2FieldValue!) {
              updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field,
                                                    value: $value}) { projectV2Item { id } } }""",
                      project=board_id, item=item_id, field=field.id, value=_field_value(field, value))

    def clear_board_value(self, repo, board_id, item_id, field_id):
        self._graphql(repo, """
            mutation($project: ID!, $item: ID!, $field: ID!) {
              clearProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field}) {
                projectV2Item { id } } }""", project=board_id, item=item_id, field=field_id)

    def _issue_items(self, repo, number):
        data = self._graphql(repo, """
            query($owner: String!, $name: String!, $number: Int!) { repository(owner: $owner, name: $name) {
              issue(number: $number) { id projectItems(first: 20) { nodes { id project { id } """ + _VALUES + """ } } } } }""",
                             number=number, **self._repo_vars(repo))
        issue = data["repository"]["issue"]
        if issue is None:
            raise TaskError(ErrorCode.TASK_NOT_FOUND, f"Issue #{number} が見つかりません。")
        return issue

    def _repo_name(self, repo):
        names = self.__dict__.setdefault("_names", {})
        if repo not in names:
            data = self._json(["repo", "view", "--json", "owner,name"], cwd=repo)
            names[repo] = (data["owner"]["login"], data["name"])
        return names[repo]

    def _repo_vars(self, repo):
        owner, name = self._repo_name(repo)
        return {"owner": owner, "name": name}

    def _graphql(self, repo, query, **variables):
        """GraphQL を呼ぶ（本文はJSONで標準入力から渡す）。権限が足りなければ board_permission。"""
        args = ["api", "graphql", "--input", "-"]
        completed = _process.run(["gh", *args], cwd=repo, check=False,
                                 input=json.dumps({"query": query, "variables": variables}),
                                 env={"GH_PROMPT_DISABLED": "1"})
        if "INSUFFICIENT_SCOPES" in completed.output or "required scopes" in completed.output:
            raise TaskError(ErrorCode.BOARD_PERMISSION, "ghのトークンに、ボード（GitHub Projects）を使う権限がありません。",
                            hint="gh auth refresh -s project を実行してください（ブラウザで承認します）。",
                            details=completed.output)
        if not completed.ok:
            match = re.search(r'"message"\s*:\s*"([^"]+)"', completed.output)
            if match and not re.search(r"HTTP 401|Bad credentials", completed.output):
                raise TaskError(ErrorCode.GITHUB_ERROR, f"GitHubに断られました：{match.group(1)}",
                                details=completed.output)
            raise _gh_error(args, completed)
        return json.loads(completed.stdout)["data"]

    def _issue_id(self, repo, number):
        """親子・依存のAPIが使う、Issueの内部のID（番号ではない）。"""
        completed = self._gh(["api", f"repos/{{owner}}/{{repo}}/issues/{number}", "--jq", ".id"], cwd=repo,
                             check=False)
        if not completed.ok:
            if _not_found(completed):
                raise TaskError(ErrorCode.TASK_NOT_FOUND, f"Issue #{number} が見つかりません。", details=completed.output)
            raise _gh_error(["api", "issues"], completed)
        return int(completed.stdout.strip())

    def _rest_issues(self, repo, path):
        output = self._gh(["api", "--paginate", f"repos/{{owner}}/{{repo}}/{path}?per_page=100", "--jq", ".[]"],
                          cwd=repo).stdout
        return [_rest_issue(json.loads(line)) for line in output.splitlines() if line.strip()]

    def _json(self, args, *, cwd):
        return json.loads(self._gh(args, cwd=cwd).stdout)

    def _gh(self, args, *, cwd, check=True):
        try:
            return _process.run(["gh", *args], cwd=cwd, check=check, env={"GH_PROMPT_DISABLED": "1"})
        except _process.ProcessFailed as failure:
            raise _gh_error(args, failure.completed) from None


def _not_found(completed: _process.Completed) -> bool:
    return re.search(r"could not resolve|not found|no pull requests? found", completed.output, re.IGNORECASE) is not None


def _gh_error(args, completed: _process.Completed) -> TaskError:
    authentication = re.search(r"auth|401|credentials", completed.output, re.IGNORECASE)
    return TaskError(
        ErrorCode.GITHUB_ERROR,
        f"gh {' '.join(args[:2])} に失敗しました。",
        hint="gh auth status で認証を確認してください。" if authentication else None,
        details=completed.output,
    )


_ISSUE_FIELDS = "number,title,url,state,body,labels,assignees,milestone"


def _issue(data: dict) -> IssueInfo:
    return IssueInfo(data["number"], data["title"], data["url"], data["state"].lower(), data.get("body") or "",
                     tuple(label["name"] for label in data.get("labels") or []),
                     tuple(user["login"] for user in data.get("assignees") or []),
                     (data.get("milestone") or {}).get("title"))


def _rest_issue(data: dict) -> IssueInfo:
    """REST API の形のIssue（gh issue view とは項目の名前が違う）。"""
    return IssueInfo(data["number"], data["title"], data.get("html_url") or "", data["state"], data.get("body") or "",
                     tuple(label["name"] for label in data.get("labels") or []),
                     tuple(user["login"] for user in data.get("assignees") or []),
                     (data.get("milestone") or {}).get("title"))


_FIELD_NAME = "field { ... on ProjectV2FieldCommon { name } }"


_VALUES = ("fieldValues(first: 50) { nodes { "
           f"... on ProjectV2ItemFieldTextValue {{ text {_FIELD_NAME} }} "
           f"... on ProjectV2ItemFieldNumberValue {{ number {_FIELD_NAME} }} "
           f"... on ProjectV2ItemFieldDateValue {{ date {_FIELD_NAME} }} "
           f"... on ProjectV2ItemFieldSingleSelectValue {{ name {_FIELD_NAME} }} "
           f"... on ProjectV2ItemFieldIterationValue {{ title {_FIELD_NAME} }} "
           "} }")


def _task_record(node: dict, board_id: str | None) -> TaskRecord:
    sub, dep = node.get("subIssuesSummary") or {}, node.get("issueDependenciesSummary") or {}
    milestone = node.get("milestone") or {}
    issue = IssueInfo(node["number"], node["title"], node["url"], node["state"].lower(), node.get("body") or "",
                      tuple(label["name"] for label in (node.get("labels") or {}).get("nodes") or []),
                      tuple(user["login"] for user in (node.get("assignees") or {}).get("nodes") or []),
                      milestone.get("title"))
    relations = IssueRelations((node.get("parent") or {}).get("number"), sub.get("total", 0), sub.get("completed", 0),
                               dep.get("blockedBy", 0), dep.get("blocking", 0))
    reason = (node.get("stateReason") or "").lower() or None
    item = None if not board_id else _board_item((node.get("projectItems") or {}).get("nodes") or [], board_id)
    return TaskRecord(issue, relations, reason if issue.state == "closed" else None,
                      (milestone.get("dueOn") or "")[:10] or None, item)


def _board_item(nodes: list, board_id: str) -> _board.BoardItem | None:
    """Issueのボードの項目のうち、そのボードのもの。値はフィールドの名前 → 表示の値（題名は除く）。"""
    for node in nodes:
        if node and node["project"]["id"] == board_id:
            values = {}
            for value in node["fieldValues"]["nodes"]:
                if not value or not value.get("field"):
                    continue
                name = value["field"]["name"]
                if name == "Title":
                    continue
                for key in ("name", "title", "text", "date", "number"):
                    if value.get(key) is not None:
                        shown = value[key]
                        if key == "number" and float(shown).is_integer():
                            shown = int(shown)
                        values[name] = str(shown)
                        break
            return _board.BoardItem(node["id"], values)
    return None


def _field_value(field: _board.BoardField, value: str) -> dict:
    """フィールドの型に合わせた値（ProjectV2FieldValue）。型に合わなければ invalid_argument。"""
    if field.type == "SINGLE_SELECT":
        return {"singleSelectOptionId": _board.find_option(field, value).id}
    if field.type == "ITERATION":
        return {"iterationId": _board.find_option(field, value).id}
    if field.type == "TEXT":
        return {"text": value}
    if field.type == "NUMBER":
        try:
            return {"number": float(value)}
        except ValueError:
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"{field.name} は数値です：{value}") from None
    if field.type == "DATE":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise TaskError(ErrorCode.INVALID_ARGUMENT, f"{field.name} は日付（YYYY-MM-DD）です：{value}")
        return {"date": value}
    raise TaskError(ErrorCode.INVALID_ARGUMENT, f"{field.name}（{field.type}）は設定できません。",
                    hint="担当者・ラベル・マイルストーン等は ecobuild task edit で変えてください。")


def _milestone(data: dict) -> MilestoneInfo:
    return MilestoneInfo(data["number"], data["title"], data["state"], data.get("html_url") or "",
                         (data.get("due_on") or "")[:10] or None, data.get("description") or "",
                         data.get("open_issues", 0), data.get("closed_issues", 0))


def _due_on(date: str) -> str:
    """期日（YYYY-MM-DD）を、APIの日時の形にする。"""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise TaskError(ErrorCode.INVALID_ARGUMENT, f"期日 {date} は YYYY-MM-DD の形で指定してください。")
    return f"{date}T23:59:59Z"


def _api_error(completed: _process.Completed) -> TaskError:
    """REST API の失敗。GitHubが返した理由（message）を見せる（親子・依存の循環・重複等）。"""
    match = re.search(r'"message"\s*:\s*"([^"]+)"', completed.output)
    if match and not re.search(r"HTTP 401|Bad credentials", completed.output):
        return TaskError(ErrorCode.GITHUB_ERROR, f"GitHubに断られました：{match.group(1)}", details=completed.output)
    return _gh_error(["api"], completed)


def _number_from_url(url: str) -> int:
    match = re.search(r"/(?:issues|pull)/(\d+)\s*$", url)
    if match is None:
        raise TaskError(ErrorCode.GITHUB_ERROR, f"gh の出力からURLを読み取れません：{url!r}")
    return int(match.group(1))
