#!/usr/bin/env python3
"""
GitHub Proxy

GitHub API および git smart HTTP protocol への権限制限付きプロキシ。
Classic PAT をホスト側に置き、AI には許可した操作のみ公開する。

Fine-grained PAT では他ユーザーのリポジトリにアクセスできない制限を回避しつつ、
必要最小限の権限のみを AI に付与する。

機能:
- GitHub REST API プロキシ（/repos/... など）
- git smart HTTP プロキシ（/git/{owner}/{repo}.git/... で clone/fetch/push）
- AWS IAM 式ポリシー評価（allow/deny ルール）

Usage:
    python main.py [--port PORT] [--config CONFIG_PATH]

設定ファイルのデフォルトパス: ~/.config/github-proxy/config.json
"""

import argparse
import base64
import fnmatch
import json
import re
import sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "github-proxy" / "config.json"
DEFAULT_PORT = 8766

# =============================================================================
# アクション体系とエンドポイントマッピング
# =============================================================================

# (method, pattern, action) のタプル
# action は層1 action (pr:xxx) または旧形式 (category:operation)
# パラメータ分岐が必要なものは _PARAM_BRANCH マーク付き（後で body を見て判定）
ENDPOINT_ACTIONS = [
    # metadata:read
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)$", "metadata:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/branches$", "metadata:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/branches/(?P<branch>[^/]+)$", "metadata:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/contributors$", "metadata:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/languages$", "metadata:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tags$", "metadata:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/topics$", "metadata:read"),

    # actions:read
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/actions/runs$", "actions:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/actions/runs/(?P<run_id>\d+)$", "actions:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/actions/runs/(?P<run_id>\d+)/jobs$", "actions:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/actions/workflows$", "actions:read"),

    # statuses:read
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/commits/(?P<ref>[^/]+)/status$", "statuses:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/commits/(?P<ref>[^/]+)/statuses$", "statuses:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/commits/(?P<ref>[^/]+)/check-runs$", "statuses:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/commits/(?P<ref>[^/]+)/check-suites$", "statuses:read"),

    # code:read
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/contents/(?P<path>.*)$", "code:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/git/refs$", "code:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/git/refs/(?P<ref>.+)$", "code:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/git/commits/(?P<sha>[^/]+)$", "code:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/git/trees/(?P<sha>[^/]+)$", "code:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/git/blobs/(?P<sha>[^/]+)$", "code:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/compare/(?P<basehead>.+)$", "code:read"),

    # code:write
    ("PUT", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/contents/(?P<path>.*)$", "code:write"),
    ("DELETE", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/contents/(?P<path>.*)$", "code:write"),
    ("POST", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/git/refs$", "code:write"),
    ("PATCH", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/git/refs/(?P<ref>.+)$", "code:write"),

    # issues:read
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues$", "issues:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<issue_number>\d+)$", "issues:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<issue_number>\d+)/comments$", "issues:read"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<issue_number>\d+)/labels$", "issues:read"),

    # issues:write
    ("POST", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues$", "issues:write"),
    ("PATCH", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<issue_number>\d+)$", "issues:write"),
    ("POST", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<issue_number>\d+)/comments$", "issues:write"),
    ("PATCH", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/comments/(?P<comment_id>\d+)$", "issues:write"),
    ("POST", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<issue_number>\d+)/labels$", "issues:write"),
    ("DELETE", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<issue_number>\d+)/labels/(?P<label>[^/]+)$", "issues:write"),

    # =========================================================================
    # PR 層1 Actions
    # =========================================================================

    # PR 基本操作 (read)
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls$", "pr:list"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)$", "pr:get"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/commits$", "pr:commits"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/files$", "pr:files"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/merge$", "pr:merge_status"),

    # PR 基本操作 (write) - パラメータ分岐は _PARAM_BRANCH で後で判定
    ("POST", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls$", "pr:create_PARAM_BRANCH"),
    ("PATCH", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)$", "pr:update_PARAM_BRANCH"),
    ("PUT", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/update-branch$", "pr:update_branch"),

    # PR merge - パラメータ分岐
    ("PUT", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/merge$", "pr:merge_PARAM_BRANCH"),

    # General Comments (Issues API 経由)
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/comments$", "pr:comment_list_all"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<issue_number>\d+)/comments$", "pr:comment_list"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/comments/(?P<comment_id>\d+)$", "pr:comment_get"),
    ("POST", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<issue_number>\d+)/comments$", "pr:comment_create"),
    ("PATCH", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/comments/(?P<comment_id>\d+)$", "pr:comment_update"),
    ("DELETE", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/comments/(?P<comment_id>\d+)$", "pr:comment_delete"),

    # Review Comments
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/comments$", "pr:review_comment_list_all"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/comments$", "pr:review_comment_list"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/comments/(?P<comment_id>\d+)$", "pr:review_comment_get"),
    ("POST", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/comments$", "pr:review_comment_create"),
    ("PATCH", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/comments/(?P<comment_id>\d+)$", "pr:review_comment_update"),
    ("DELETE", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/comments/(?P<comment_id>\d+)$", "pr:review_comment_delete"),
    ("POST", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/comments/(?P<comment_id>\d+)/replies$", "pr:review_comment_reply"),

    # Reviews
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/reviews$", "pr:review_list"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/reviews/(?P<review_id>\d+)$", "pr:review_get"),
    ("POST", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/reviews$", "pr:review_PARAM_BRANCH"),
    ("PUT", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/reviews/(?P<review_id>\d+)$", "pr:review_update"),
    ("DELETE", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/reviews/(?P<review_id>\d+)$", "pr:review_delete"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/reviews/(?P<review_id>\d+)/comments$", "pr:review_comments"),
    ("PUT", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/reviews/(?P<review_id>\d+)/dismissals$", "pr:review_dismiss"),
    ("POST", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/reviews/(?P<review_id>\d+)/events$", "pr:review_submit_PARAM_BRANCH"),

    # Review Requests
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/requested_reviewers$", "pr:reviewer_list"),
    ("POST", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/requested_reviewers$", "pr:reviewer_request"),
    ("DELETE", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/requested_reviewers$", "pr:reviewer_remove"),
]

# git smart HTTP protocol のエンドポイント
GIT_ENDPOINT_ACTIONS = [
    # git:read (clone, fetch)
    ("GET", r"/git/(?P<owner>[^/]+)/(?P<repo>[^/]+)\.git/info/refs$", "git:read"),  # service=git-upload-pack
    ("POST", r"/git/(?P<owner>[^/]+)/(?P<repo>[^/]+)\.git/git-upload-pack$", "git:read"),
    # git:write (push)
    ("POST", r"/git/(?P<owner>[^/]+)/(?P<repo>[^/]+)\.git/git-receive-pack$", "git:write"),
]

# GraphQL mutation → action マッピング
GRAPHQL_MUTATION_ACTIONS = {
    "addDiscussionComment": "discussions:write",
}

# =============================================================================
# 層1 Primitive Actions (PR)
# =============================================================================

PR_LAYER1_ACTIONS = [
    # PR 基本操作
    "pr:list", "pr:get", "pr:create", "pr:create_draft", "pr:update",
    "pr:close", "pr:reopen", "pr:convert_to_draft", "pr:mark_ready",
    "pr:commits", "pr:files", "pr:merge_status",
    "pr:merge_commit", "pr:merge_squash", "pr:merge_rebase",
    "pr:update_branch",
    # General Comments
    "pr:comment_list_all", "pr:comment_list", "pr:comment_get",
    "pr:comment_create", "pr:comment_update", "pr:comment_delete",
    # Review Comments
    "pr:review_comment_list_all", "pr:review_comment_list", "pr:review_comment_get",
    "pr:review_comment_create", "pr:review_comment_update", "pr:review_comment_delete",
    "pr:review_comment_reply",
    # Reviews
    "pr:review_list", "pr:review_get", "pr:review_pending",
    "pr:approve", "pr:request_changes", "pr:review_comment_only",
    "pr:review_update", "pr:review_delete", "pr:review_comments",
    "pr:review_dismiss",
    "pr:review_submit_approve", "pr:review_submit_request_changes", "pr:review_submit_comment",
    # Review Requests
    "pr:reviewer_list", "pr:reviewer_request", "pr:reviewer_remove",
]

# =============================================================================
# 層2 Bundle 定義
# =============================================================================

# pull-requests:read に含まれる層1 actions
PULL_REQUESTS_READ_ACTIONS = [
    "pr:list", "pr:get", "pr:commits", "pr:files", "pr:merge_status",
    "pr:reviewer_list", "pr:review_list", "pr:review_get", "pr:review_comments",
    "pr:review_comment_list_all", "pr:review_comment_list", "pr:review_comment_get",
    "pr:comment_list_all", "pr:comment_list", "pr:comment_get",
]

# pull-requests:write に追加される層1 actions (read は含まない)
PULL_REQUESTS_WRITE_ONLY_ACTIONS = [
    "pr:create", "pr:create_draft", "pr:update", "pr:close", "pr:reopen",
    "pr:convert_to_draft", "pr:mark_ready", "pr:update_branch",
    "pr:reviewer_request", "pr:reviewer_remove",
    "pr:review_pending", "pr:approve", "pr:request_changes", "pr:review_comment_only",
    "pr:review_update", "pr:review_delete", "pr:review_dismiss",
    "pr:review_submit_approve", "pr:review_submit_request_changes", "pr:review_submit_comment",
    "pr:review_comment_create", "pr:review_comment_update", "pr:review_comment_delete",
    "pr:review_comment_reply",
    "pr:comment_create", "pr:comment_update", "pr:comment_delete",
]

# pulls:contribute に追加される層1 actions (read は含まない)
PULLS_CONTRIBUTE_ONLY_ACTIONS = [
    "pr:create", "pr:create_draft", "pr:update",
    "pr:convert_to_draft", "pr:mark_ready",
    "pr:comment_create", "pr:comment_update",
    "pr:review_comment_create", "pr:review_comment_update", "pr:review_comment_reply",
    "pr:review_pending", "pr:approve", "pr:request_changes", "pr:review_comment_only",
    "pr:review_update",
    "pr:review_submit_approve", "pr:review_submit_request_changes", "pr:review_submit_comment",
    "pr:reviewer_request",
]

# 層2 Bundle → 層1 展開マッピング
BUNDLE_EXPANSION = {
    "pull-requests:read": PULL_REQUESTS_READ_ACTIONS,
    "pull-requests:write": PULL_REQUESTS_READ_ACTIONS + PULL_REQUESTS_WRITE_ONLY_ACTIONS,
    "pulls:contribute": PULL_REQUESTS_READ_ACTIONS + PULLS_CONTRIBUTE_ONLY_ACTIONS,
}

# ワイルドカード展開用のアクション一覧
ALL_ACTIONS = [
    "metadata:read",
    "actions:read",
    "statuses:read",
    "code:read", "code:write",
    "issues:read", "issues:write",
    "git:read", "git:write",
    "discussions:write",
    "subissues:add", "subissues:remove", "subissues:reprioritize",
] + PR_LAYER1_ACTIONS

# カテゴリごとのアクション（ワイルドカード展開用）
ACTION_CATEGORIES = {
    "metadata": ["metadata:read"],
    "actions": ["actions:read"],
    "statuses": ["statuses:read"],
    "code": ["code:read", "code:write"],
    "issues": ["issues:read", "issues:write"],
    "pr": PR_LAYER1_ACTIONS,
    "git": ["git:read", "git:write"],
    "discussions": ["discussions:write"],
    "subissues": ["subissues:add", "subissues:remove", "subissues:reprioritize"],
}


# =============================================================================
# ポリシー評価
# =============================================================================

def expand_action_pattern(pattern: str) -> list[str]:
    """
    アクションパターンを展開する
    - "*" → 全アクション
    - "issues:*" → issues:read, issues:write
    - "pull-requests:read" → 層1 actions に展開
    - "pulls:contribute" → 層1 actions に展開
    - "pr:list" → pr:list (層1 action そのまま)
    """
    if pattern == "*":
        return ALL_ACTIONS.copy()

    # 層2 Bundle 展開
    if pattern in BUNDLE_EXPANSION:
        return BUNDLE_EXPANSION[pattern].copy()

    # カテゴリワイルドカード展開
    if pattern.endswith(":*"):
        category = pattern[:-2]
        if category in ACTION_CATEGORIES:
            return ACTION_CATEGORIES[category].copy()
        return []

    # 層1 action または旧 action
    if pattern in ALL_ACTIONS:
        return [pattern]

    return []


def expand_repo_pattern(pattern: str, repo: str) -> bool:
    """
    リポジトリパターンがマッチするかチェック（case-insensitive）
    - "*" → 全リポジトリ
    - "owner/*" → owner の全リポジトリ
    - "owner/repo" → 完全一致
    """
    pattern_lower = pattern.lower()
    repo_lower = repo.lower()

    if pattern_lower == "*":
        return True

    if pattern_lower.endswith("/*"):
        owner_pattern = pattern_lower[:-2]
        repo_owner = repo_lower.split("/")[0]
        return owner_pattern == repo_owner

    return fnmatch.fnmatch(repo_lower, pattern_lower)


def evaluate_policy(action: str, repo: str, rules: list[dict]) -> tuple[bool, str]:
    """
    AWS IAM 式のポリシー評価

    評価ロジック:
    1. デフォルト: 暗黙の Deny
    2. 一つでも Deny にマッチ → 即拒否（Deny always wins）
    3. 一つでも Allow にマッチ → 許可
    4. 何もマッチしない → 拒否

    Returns: (allowed, reason)
    """
    has_allow = False

    for rule in rules:
        effect = rule.get("effect", "").lower()
        actions = rule.get("actions", [])
        repos = rule.get("repos", [])

        # アクションがマッチするか
        action_match = False
        for action_pattern in actions:
            expanded = expand_action_pattern(action_pattern)
            if action in expanded:
                action_match = True
                break

        if not action_match:
            continue

        # リポジトリがマッチするか
        repo_match = False
        for repo_pattern in repos:
            if expand_repo_pattern(repo_pattern, repo):
                repo_match = True
                break

        if not repo_match:
            continue

        # 両方マッチした場合
        if effect == "deny":
            return False, f"Denied by rule: {rule}"
        elif effect == "allow":
            has_allow = True

    if has_allow:
        return True, "Allowed"
    else:
        return False, f"No matching allow rule for {action} on {repo}"


# =============================================================================
# パラメータ分岐
# =============================================================================

def resolve_param_branch(action: str, body: bytes | None) -> str:
    """
    _PARAM_BRANCH マーク付きの action をリクエストボディに基づいて解決する

    パラメータ分岐:
    - pr:create_PARAM_BRANCH → draft で pr:create or pr:create_draft
    - pr:update_PARAM_BRANCH → state/draft で pr:update, pr:close, pr:reopen, pr:convert_to_draft, pr:mark_ready
    - pr:merge_PARAM_BRANCH → merge_method で pr:merge_commit, pr:merge_squash, pr:merge_rebase
    - pr:review_PARAM_BRANCH → event で pr:review_pending, pr:approve, pr:request_changes, pr:review_comment_only
    - pr:review_submit_PARAM_BRANCH → event で pr:review_submit_approve, pr:review_submit_request_changes, pr:review_submit_comment
    """
    if "_PARAM_BRANCH" not in action:
        return action

    # ボディをパース
    body_json = {}
    if body:
        try:
            body_json = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    # pr:create_PARAM_BRANCH
    if action == "pr:create_PARAM_BRANCH":
        if body_json.get("draft", False):
            return "pr:create_draft"
        return "pr:create"

    # pr:update_PARAM_BRANCH
    if action == "pr:update_PARAM_BRANCH":
        state = body_json.get("state")
        draft = body_json.get("draft")

        if state == "closed":
            return "pr:close"
        if state == "open":
            return "pr:reopen"
        if draft is True:
            return "pr:convert_to_draft"
        if draft is False:
            return "pr:mark_ready"
        return "pr:update"

    # pr:merge_PARAM_BRANCH
    if action == "pr:merge_PARAM_BRANCH":
        merge_method = body_json.get("merge_method", "merge")
        if merge_method == "squash":
            return "pr:merge_squash"
        if merge_method == "rebase":
            return "pr:merge_rebase"
        return "pr:merge_commit"

    # pr:review_PARAM_BRANCH
    if action == "pr:review_PARAM_BRANCH":
        event = body_json.get("event", "").upper()
        if event == "APPROVE":
            return "pr:approve"
        if event == "REQUEST_CHANGES":
            return "pr:request_changes"
        if event == "COMMENT":
            return "pr:review_comment_only"
        return "pr:review_pending"

    # pr:review_submit_PARAM_BRANCH
    if action == "pr:review_submit_PARAM_BRANCH":
        event = body_json.get("event", "").upper()
        if event == "APPROVE":
            return "pr:review_submit_approve"
        if event == "REQUEST_CHANGES":
            return "pr:review_submit_request_changes"
        return "pr:review_submit_comment"

    # 未知の _PARAM_BRANCH（フォールバック）
    return action.replace("_PARAM_BRANCH", "")


# =============================================================================
# エンドポイントマッチング
# =============================================================================

def match_endpoint(method: str, path: str) -> tuple[str | None, dict]:
    """
    エンドポイントがマッチするかチェック
    Returns: (action, captured_groups) or (None, {})
    """
    for allowed_method, pattern, action in ENDPOINT_ACTIONS:
        if method != allowed_method:
            continue
        match = re.match(pattern, path)
        if match:
            return action, match.groupdict()
    return None, {}


def match_git_endpoint(method: str, path: str, query: str) -> tuple[str | None, dict]:
    """
    git smart HTTP エンドポイントにマッチするかチェック
    info/refs の場合は service パラメータで read/write を判定
    Returns: (action, captured_groups) or (None, {})
    """
    for allowed_method, pattern, action in GIT_ENDPOINT_ACTIONS:
        if method != allowed_method:
            continue
        match = re.match(pattern, path)
        if match:
            # info/refs の場合、service パラメータで判定
            if path.endswith("/info/refs"):
                if "service=git-receive-pack" in query:
                    return "git:write", match.groupdict()
                else:
                    return "git:read", match.groupdict()
            return action, match.groupdict()
    return None, {}


# =============================================================================
# 設定ファイル
# =============================================================================

def load_config(config_path: Path) -> dict:
    """設定ファイルを読み込む"""
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        print(f"\nCreate the config file with:", file=sys.stderr)
        print(f"  mkdir -p {config_path.parent}", file=sys.stderr)
        print(f"  cat > {config_path} << 'EOF'", file=sys.stderr)
        print("""{
  "classic_pat": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "rules": [
    { "effect": "allow", "actions": ["*"], "repos": ["owner/repo"] },
    { "effect": "deny", "actions": ["pulls:merge"], "repos": ["*"] }
  ]
}
EOF""", file=sys.stderr)
        sys.exit(1)

    # 設定ファイルの権限チェック（600 以外は拒否）
    stat_info = config_path.stat()
    if stat_info.st_mode & 0o077:
        print(f"Error: Config file has insecure permissions: {oct(stat_info.st_mode)[-3:]}", file=sys.stderr)
        print(f"Run: chmod 600 {config_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(config_path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}", file=sys.stderr)
        sys.exit(1)

    # 必須フィールドチェック
    if "classic_pat" not in config:
        print("Error: Missing required field: classic_pat", file=sys.stderr)
        sys.exit(1)

    if "rules" not in config:
        print("Error: Missing required field: rules", file=sys.stderr)
        sys.exit(1)

    if not isinstance(config["rules"], list) or len(config["rules"]) == 0:
        print("Error: rules must be a non-empty list", file=sys.stderr)
        sys.exit(1)

    # ルールのバリデーション
    for i, rule in enumerate(config["rules"]):
        if "effect" not in rule:
            print(f"Error: Rule {i} missing 'effect'", file=sys.stderr)
            sys.exit(1)
        if rule["effect"] not in ["allow", "deny"]:
            print(f"Error: Rule {i} effect must be 'allow' or 'deny'", file=sys.stderr)
            sys.exit(1)
        if "actions" not in rule or not isinstance(rule["actions"], list):
            print(f"Error: Rule {i} missing or invalid 'actions'", file=sys.stderr)
            sys.exit(1)
        if "repos" not in rule or not isinstance(rule["repos"], list):
            print(f"Error: Rule {i} missing or invalid 'repos'", file=sys.stderr)
            sys.exit(1)

    return config


# =============================================================================
# HTTP ハンドラ
# =============================================================================

class GitHubProxyHandler(BaseHTTPRequestHandler):
    """GitHub API および git smart HTTP へのプロキシハンドラ"""

    config: dict = {}

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")

    def route_request(self, method: str):
        """リクエストを適切なハンドラにルーティング"""
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/git/"):
            self.handle_git_request(method)
        elif path == "/graphql":
            self.handle_graphql_request(method)
        elif path.startswith("/graphql-ops/sub-issues/"):
            self.handle_sub_issues_request(method, path)
        else:
            self.handle_api_request(method)

    def handle_git_request(self, method: str):
        """git smart HTTP protocol のリクエスト処理"""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parsed.query

        # エンドポイントマッチング
        action, groups = match_git_endpoint(method, path, query)
        if action is None:
            self.send_error(403, f"Git endpoint not allowed: {method} {path}")
            return

        # リポジトリ取得
        owner = groups.get("owner")
        repo = groups.get("repo")
        if not owner or not repo:
            self.send_error(400, "Could not determine repository")
            return

        full_repo = f"{owner}/{repo}"

        # ポリシー評価
        allowed, reason = evaluate_policy(action, full_repo, self.config["rules"])
        if not allowed:
            self.send_error(403, reason)
            return

        # リクエストボディの読み取り
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # GitHub にプロキシ
        try:
            response_data, response_headers, status_code = self.proxy_git_to_github(
                method, owner, repo, path, query, body
            )
            self.send_response(status_code)
            if "Content-Type" in response_headers:
                self.send_header("Content-Type", response_headers["Content-Type"])
            if "Cache-Control" in response_headers:
                self.send_header("Cache-Control", response_headers["Cache-Control"])
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response_data)
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self.send_error(e.code, f"{e.reason}: {error_body[:200]}")
        except URLError as e:
            self.send_error(502, f"Failed to connect to GitHub: {e.reason}")
        except Exception as e:
            self.send_error(500, str(e))

    def proxy_git_to_github(
        self, method: str, owner: str, repo: str, path: str, query: str, body: bytes | None
    ) -> tuple[bytes, dict, int]:
        """git smart HTTP を GitHub にプロキシ"""
        git_path = path.replace(f"/git/{owner}/{repo}.git", f"/{owner}/{repo}.git")
        url = f"https://github.com{git_path}"
        if query:
            url += f"?{query}"

        pat = self.config["classic_pat"]
        credentials = base64.b64encode(f"x-access-token:{pat}".encode()).decode()

        headers = {
            "Authorization": f"Basic {credentials}",
            "User-Agent": "git/2.40.0",
        }

        if self.headers.get("Content-Type"):
            headers["Content-Type"] = self.headers.get("Content-Type")

        if self.headers.get("Accept"):
            headers["Accept"] = self.headers.get("Accept")

        req = Request(url, data=body, headers=headers, method=method)

        with urlopen(req, timeout=60) as response:
            response_headers = {k: v for k, v in response.headers.items()}
            return response.read(), response_headers, response.status

    def handle_graphql_request(self, method: str):
        """GraphQL リクエスト処理"""
        if method != "POST":
            self.send_error(405, "GraphQL only supports POST")
            return

        # リクエストボディの読み取り
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_error(400, "Request body required")
            return

        body = self.rfile.read(content_length)

        try:
            body_json = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON in request body")
            return

        query = body_json.get("query", "")

        # mutation 名を抽出
        mutation_match = re.search(r"mutation\s*\{?\s*(\w+)", query)
        if not mutation_match:
            self.send_error(403, "Only mutations are supported via proxy")
            return

        mutation_name = mutation_match.group(1)

        # mutation → action マッピング
        action = GRAPHQL_MUTATION_ACTIONS.get(mutation_name)
        if action is None:
            self.send_error(403, f"Mutation not allowed: {mutation_name}")
            return

        # GraphQL の場合、リポジトリは config の graphql_repos から取得
        graphql_repos = self.config.get("graphql_repos", [])
        if not graphql_repos:
            self.send_error(403, "No graphql_repos configured")
            return

        # いずれかの repo で許可されているかチェック
        allowed = False
        for repo in graphql_repos:
            is_allowed, reason = evaluate_policy(action, repo, self.config["rules"])
            if is_allowed:
                allowed = True
                break

        if not allowed:
            self.send_error(403, f"Action {action} not allowed on any graphql_repos")
            return

        # GitHub GraphQL API にプロキシ
        try:
            response_data, response_headers = self.proxy_graphql_to_github(body)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response_data)
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self.send_error(e.code, f"{e.reason}: {error_body[:200]}")
        except URLError as e:
            self.send_error(502, f"Failed to connect to GitHub: {e.reason}")
        except Exception as e:
            self.send_error(500, str(e))

    def proxy_graphql_to_github(self, body: bytes) -> tuple[bytes, dict]:
        """GitHub GraphQL API にプロキシ"""
        url = "https://api.github.com/graphql"

        headers = {
            "Authorization": f"bearer {self.config['classic_pat']}",
            "Content-Type": "application/json",
            "User-Agent": "github-proxy/1.0",
        }

        req = Request(url, data=body, headers=headers, method="POST")

        with urlopen(req, timeout=30) as response:
            response_headers = {k: v for k, v in response.headers.items()}
            return response.read(), response_headers

    # =========================================================================
    # Sub-Issues GraphQL Operations
    # =========================================================================

    def handle_sub_issues_request(self, method: str, path: str):
        """Sub-issues GraphQL operations の REST 風エンドポイント"""
        if method != "POST":
            self.send_error(405, "Only POST is allowed")
            return

        # リクエストボディの読み取り
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_error(400, "Request body required")
            return

        body = self.rfile.read(content_length)

        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON in request body")
            return

        # 必須パラメータの検証
        owner = data.get("owner")
        repo = data.get("repo")
        issue_number = data.get("issue_number")
        sub_issue_number = data.get("sub_issue_number")

        if not owner or not repo:
            self.send_error(400, "owner and repo are required")
            return

        full_repo = f"{owner}/{repo}"

        # オペレーション判定
        if path == "/graphql-ops/sub-issues/add":
            action = "subissues:add"
        elif path == "/graphql-ops/sub-issues/remove":
            action = "subissues:remove"
        elif path == "/graphql-ops/sub-issues/reprioritize":
            action = "subissues:reprioritize"
        else:
            self.send_error(404, f"Unknown sub-issues operation: {path}")
            return

        # ポリシー評価
        allowed, reason = evaluate_policy(action, full_repo, self.config["rules"])
        if not allowed:
            self.send_error(403, reason)
            return

        # オペレーション実行
        try:
            if action == "subissues:add":
                if not issue_number or not sub_issue_number:
                    self.send_error(400, "issue_number and sub_issue_number are required")
                    return
                result = self.execute_add_sub_issue(
                    owner, repo, issue_number, sub_issue_number,
                    replace_parent=data.get("replace_parent", False)
                )
            elif action == "subissues:remove":
                if not issue_number or not sub_issue_number:
                    self.send_error(400, "issue_number and sub_issue_number are required")
                    return
                result = self.execute_remove_sub_issue(owner, repo, issue_number, sub_issue_number)
            elif action == "subissues:reprioritize":
                if not issue_number or not sub_issue_number:
                    self.send_error(400, "issue_number and sub_issue_number are required")
                    return
                result = self.execute_reprioritize_sub_issue(
                    owner, repo, issue_number, sub_issue_number,
                    before_number=data.get("before_number"),
                    after_number=data.get("after_number")
                )

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))

        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self.send_error(e.code, f"{e.reason}: {error_body[:200]}")
        except URLError as e:
            self.send_error(502, f"Failed to connect to GitHub: {e.reason}")
        except ValueError as e:
            self.send_error(400, str(e))
        except Exception as e:
            self.send_error(500, str(e))

    def get_issue_node_id(self, owner: str, repo: str, issue_number: int) -> str:
        """Issue の Node ID を取得"""
        query = """
        query($owner: String!, $repo: String!, $number: Int!) {
            repository(owner: $owner, name: $repo) {
                issue(number: $number) {
                    id
                }
            }
        }
        """
        variables = {"owner": owner, "repo": repo, "number": issue_number}
        result = self.execute_graphql(query, variables)

        issue = result.get("data", {}).get("repository", {}).get("issue")
        if not issue:
            raise ValueError(f"Issue #{issue_number} not found in {owner}/{repo}")
        return issue["id"]

    def execute_graphql(self, query: str, variables: dict = None) -> dict:
        """GraphQL クエリを実行"""
        url = "https://api.github.com/graphql"

        body = {"query": query}
        if variables:
            body["variables"] = variables

        headers = {
            "Authorization": f"bearer {self.config['classic_pat']}",
            "Content-Type": "application/json",
            "User-Agent": "github-proxy/1.0",
        }

        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")

        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            if "errors" in result:
                raise ValueError(f"GraphQL error: {result['errors']}")
            return result

    def execute_add_sub_issue(
        self, owner: str, repo: str, issue_number: int, sub_issue_number: int,
        replace_parent: bool = False
    ) -> dict:
        """addSubIssue mutation を実行"""
        issue_id = self.get_issue_node_id(owner, repo, issue_number)
        sub_issue_id = self.get_issue_node_id(owner, repo, sub_issue_number)

        mutation = """
        mutation($issueId: ID!, $subIssueId: ID!, $replaceParent: Boolean) {
            addSubIssue(input: {issueId: $issueId, subIssueId: $subIssueId, replaceParent: $replaceParent}) {
                issue { number }
                subIssue { number }
            }
        }
        """
        variables = {
            "issueId": issue_id,
            "subIssueId": sub_issue_id,
            "replaceParent": replace_parent
        }
        result = self.execute_graphql(mutation, variables)

        return {
            "success": True,
            "issue_number": issue_number,
            "sub_issue_number": sub_issue_number
        }

    def execute_remove_sub_issue(
        self, owner: str, repo: str, issue_number: int, sub_issue_number: int
    ) -> dict:
        """removeSubIssue mutation を実行"""
        issue_id = self.get_issue_node_id(owner, repo, issue_number)
        sub_issue_id = self.get_issue_node_id(owner, repo, sub_issue_number)

        mutation = """
        mutation($issueId: ID!, $subIssueId: ID!) {
            removeSubIssue(input: {issueId: $issueId, subIssueId: $subIssueId}) {
                issue { number }
                subIssue { number }
            }
        }
        """
        variables = {"issueId": issue_id, "subIssueId": sub_issue_id}
        result = self.execute_graphql(mutation, variables)

        return {
            "success": True,
            "issue_number": issue_number,
            "sub_issue_number": sub_issue_number
        }

    def execute_reprioritize_sub_issue(
        self, owner: str, repo: str, issue_number: int, sub_issue_number: int,
        before_number: int = None, after_number: int = None
    ) -> dict:
        """reprioritizeSubIssue mutation を実行"""
        issue_id = self.get_issue_node_id(owner, repo, issue_number)
        sub_issue_id = self.get_issue_node_id(owner, repo, sub_issue_number)

        before_id = None
        after_id = None
        if before_number:
            before_id = self.get_issue_node_id(owner, repo, before_number)
        if after_number:
            after_id = self.get_issue_node_id(owner, repo, after_number)

        mutation = """
        mutation($issueId: ID!, $subIssueId: ID!, $beforeId: ID, $afterId: ID) {
            reprioritizeSubIssue(input: {issueId: $issueId, subIssueId: $subIssueId, beforeId: $beforeId, afterId: $afterId}) {
                issue { number }
            }
        }
        """
        variables = {
            "issueId": issue_id,
            "subIssueId": sub_issue_id,
            "beforeId": before_id,
            "afterId": after_id
        }
        result = self.execute_graphql(mutation, variables)

        return {
            "success": True,
            "issue_number": issue_number,
            "sub_issue_number": sub_issue_number,
            "before_number": before_number,
            "after_number": after_number
        }

    def handle_api_request(self, method: str):
        """GitHub API リクエスト処理"""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parsed.query

        # エンドポイントマッチング
        action, groups = match_endpoint(method, path)
        if action is None:
            self.send_error(403, f"Endpoint not allowed: {method} {path}")
            return

        # リポジトリ取得
        owner = groups.get("owner")
        repo = groups.get("repo")
        if not owner or not repo:
            self.send_error(400, "Could not determine repository")
            return

        full_repo = f"{owner}/{repo}"

        # リクエストボディの読み取り（パラメータ分岐で必要）
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # パラメータ分岐（_PARAM_BRANCH を解決）
        action = resolve_param_branch(action, body)

        # ポリシー評価
        allowed, reason = evaluate_policy(action, full_repo, self.config["rules"])
        if not allowed:
            self.send_error(403, reason)
            return

        # GitHub API にプロキシ
        try:
            response_data, response_headers = self.proxy_to_github(method, path, query, body)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            for header in ["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"]:
                if header in response_headers:
                    self.send_header(header, response_headers[header])
            self.end_headers()
            self.wfile.write(response_data)
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self.send_error(e.code, f"{e.reason}: {error_body[:200]}")
        except URLError as e:
            self.send_error(502, f"Failed to connect to GitHub: {e.reason}")
        except Exception as e:
            self.send_error(500, str(e))

    def proxy_to_github(self, method: str, path: str, query: str, body: bytes | None) -> tuple[bytes, dict]:
        """GitHub API にプロキシ"""
        url = f"https://api.github.com{path}"
        if query:
            url += f"?{query}"

        headers = {
            "Authorization": f"token {self.config['classic_pat']}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-proxy/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if body:
            headers["Content-Type"] = "application/json"

        req = Request(url, data=body, headers=headers, method=method)

        with urlopen(req, timeout=30) as response:
            response_headers = {k: v for k, v in response.headers.items()}
            return response.read(), response_headers

    def do_GET(self):
        self.route_request("GET")

    def do_POST(self):
        self.route_request("POST")

    def do_PUT(self):
        self.route_request("PUT")

    def do_PATCH(self):
        self.route_request("PATCH")

    def do_DELETE(self):
        self.route_request("DELETE")

    def do_OPTIONS(self):
        """CORS preflight"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


# =============================================================================
# メイン
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="GitHub Proxy")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"Port to listen on (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Config file path (default: {DEFAULT_CONFIG_PATH})",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    GitHubProxyHandler.config = config

    server = HTTPServer(("0.0.0.0", args.port), GitHubProxyHandler)
    print(f"GitHub Proxy listening on http://0.0.0.0:{args.port}")
    print(f"Config: {args.config}")

    print(f"\nSupported actions:")
    for category, actions in ACTION_CATEGORIES.items():
        print(f"  {category}: {', '.join(a.split(':')[1] for a in actions)}")

    print(f"\nPolicy rules: {len(config['rules'])}")
    for i, rule in enumerate(config["rules"]):
        effect = rule["effect"].upper()
        actions = ", ".join(rule["actions"])
        repos = ", ".join(rule["repos"])
        print(f"  [{i}] {effect}: {actions} on {repos}")

    print("\nPress Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
