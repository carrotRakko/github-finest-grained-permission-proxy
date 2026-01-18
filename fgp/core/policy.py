"""
Policy evaluation and endpoint matching.

AWS IAM-style policy evaluation for GitHub API access control.
"""

import fnmatch
import json
import re
import sys
from pathlib import Path

import json5

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "github-proxy" / "config.json"
DEFAULT_PORT = 8766

# =============================================================================
# Endpoint → Action Mapping
# =============================================================================

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

    # PR Layer 1 Actions
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls$", "pr:list"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)$", "pr:get"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/commits$", "pr:commits"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/files$", "pr:files"),
    ("GET", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/merge$", "pr:merge_status"),
    ("POST", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls$", "pr:create_PARAM_BRANCH"),
    ("PATCH", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)$", "pr:update_PARAM_BRANCH"),
    ("PUT", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/update-branch$", "pr:update_branch"),
    ("PUT", r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<pull_number>\d+)/merge$", "pr:merge_PARAM_BRANCH"),

    # General Comments (Issues API)
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

GIT_ENDPOINT_ACTIONS = [
    ("GET", r"/git/(?P<owner>[^/]+)/(?P<repo>[^/]+)\.git/info/refs$", "git:read"),
    ("POST", r"/git/(?P<owner>[^/]+)/(?P<repo>[^/]+)\.git/git-upload-pack$", "git:read"),
    ("POST", r"/git/(?P<owner>[^/]+)/(?P<repo>[^/]+)\.git/git-receive-pack$", "git:write"),
]

GRAPHQL_MUTATION_ACTIONS = {
    "addDiscussionComment": "discussions:comment_add",
}

# =============================================================================
# Layer 1/2 Action Definitions
# =============================================================================

PR_LAYER1_ACTIONS = [
    "pr:list", "pr:get", "pr:create", "pr:create_draft", "pr:update",
    "pr:close", "pr:reopen", "pr:convert_to_draft", "pr:mark_ready",
    "pr:commits", "pr:files", "pr:merge_status",
    "pr:merge_commit", "pr:merge_squash", "pr:merge_rebase",
    "pr:update_branch",
    "pr:comment_list_all", "pr:comment_list", "pr:comment_get",
    "pr:comment_create", "pr:comment_update", "pr:comment_delete",
    "pr:review_comment_list_all", "pr:review_comment_list", "pr:review_comment_get",
    "pr:review_comment_create", "pr:review_comment_update", "pr:review_comment_delete",
    "pr:review_comment_reply",
    "pr:review_list", "pr:review_get", "pr:review_pending",
    "pr:approve", "pr:request_changes", "pr:review_comment_only",
    "pr:review_update", "pr:review_delete", "pr:review_comments",
    "pr:review_dismiss",
    "pr:review_submit_approve", "pr:review_submit_request_changes", "pr:review_submit_comment",
    "pr:reviewer_list", "pr:reviewer_request", "pr:reviewer_remove",
]

PULL_REQUESTS_READ_ACTIONS = [
    "pr:list", "pr:get", "pr:commits", "pr:files", "pr:merge_status",
    "pr:reviewer_list", "pr:review_list", "pr:review_get", "pr:review_comments",
    "pr:review_comment_list_all", "pr:review_comment_list", "pr:review_comment_get",
    "pr:comment_list_all", "pr:comment_list", "pr:comment_get",
]

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

BUNDLE_EXPANSION = {
    "pull-requests:read": PULL_REQUESTS_READ_ACTIONS,
    "pull-requests:write": PULL_REQUESTS_READ_ACTIONS + PULL_REQUESTS_WRITE_ONLY_ACTIONS,
    "pulls:contribute": PULL_REQUESTS_READ_ACTIONS + PULLS_CONTRIBUTE_ONLY_ACTIONS,
    "pr:merge": ["pr:merge_commit", "pr:merge_squash", "pr:merge_rebase"],
}

# This will be populated by commands registering their actions
_COMMAND_ACTIONS: list[str] = []

def register_actions(actions: list[str]) -> None:
    """Register actions from a command module."""
    for action in actions:
        if action not in _COMMAND_ACTIONS:
            _COMMAND_ACTIONS.append(action)

def get_all_actions() -> list[str]:
    """Get all registered actions."""
    base_actions = [
        "metadata:read",
        "actions:read",
        "statuses:read",
        "code:read", "code:write",
        "issues:read", "issues:write",
        "git:read", "git:write",
        "pr:read", "pr:create", "pr:write", "pr:merge", "pr:comment", "pr:review",
    ]
    return base_actions + PR_LAYER1_ACTIONS + _COMMAND_ACTIONS

# Discussion Layer 1 actions
DISCUSSION_LAYER1_ACTIONS = [
    "discussions:list",
    "discussions:get",
    "discussions:create",
    "discussions:update",
    "discussions:close",
    "discussions:reopen",
    "discussions:delete",
    "discussions:comment_list",
    "discussions:comment_add",
    "discussions:comment_edit",
    "discussions:comment_delete",
    "discussions:answer",
    "discussions:unanswer",
    "discussions:poll_vote",
]

# For backward compatibility
ALL_ACTIONS = [
    "metadata:read",
    "actions:read",
    "statuses:read",
    "code:read", "code:write",
    "issues:read", "issues:write",
    "git:read", "git:write",
    "subissues:list", "subissues:parent", "subissues:add", "subissues:remove", "subissues:reprioritize",
    "pr:read", "pr:create", "pr:write", "pr:merge", "pr:comment", "pr:review",
] + PR_LAYER1_ACTIONS + DISCUSSION_LAYER1_ACTIONS

ACTION_CATEGORIES = {
    "metadata": ["metadata:read"],
    "actions": ["actions:read"],
    "statuses": ["statuses:read"],
    "code": ["code:read", "code:write"],
    "issues": ["issues:read", "issues:write"],
    "pr": ["pr:read", "pr:create", "pr:write", "pr:merge", "pr:comment", "pr:review"] + PR_LAYER1_ACTIONS,
    "git": ["git:read", "git:write"],
    "discussions": DISCUSSION_LAYER1_ACTIONS,
    "subissues": ["subissues:list", "subissues:parent", "subissues:add", "subissues:remove", "subissues:reprioritize"],
}


# =============================================================================
# Policy Evaluation
# =============================================================================

def expand_action_pattern(pattern: str) -> list[str]:
    """
    Expand action pattern.
    - "*" → all actions
    - "issues:*" → issues:read, issues:write
    - "pull-requests:read" → layer 1 actions
    - "pr:list" → pr:list (layer 1 action as-is)
    """
    if pattern == "*":
        return ALL_ACTIONS.copy()

    if pattern in BUNDLE_EXPANSION:
        return BUNDLE_EXPANSION[pattern].copy()

    if pattern.endswith(":*"):
        category = pattern[:-2]
        if category in ACTION_CATEGORIES:
            return ACTION_CATEGORIES[category].copy()
        return []

    if pattern in ALL_ACTIONS:
        return [pattern]

    return []


def expand_repo_pattern(pattern: str, repo: str) -> bool:
    """
    Check if repo pattern matches (case-insensitive).
    - "*" → all repos
    - "owner/*" → all repos of owner
    - "owner/repo" → exact match
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
    AWS IAM-style policy evaluation.

    Logic:
    1. Default: implicit deny
    2. Any deny match → reject (deny always wins)
    3. Any allow match → allow
    4. No match → reject
    """
    has_allow = False

    for rule in rules:
        effect = rule.get("effect", "").lower()
        actions = rule.get("actions", [])
        repos = rule.get("repos", [])

        action_match = False
        for action_pattern in actions:
            expanded = expand_action_pattern(action_pattern)
            if action in expanded:
                action_match = True
                break

        if not action_match:
            continue

        repo_match = False
        for repo_pattern in repos:
            if expand_repo_pattern(repo_pattern, repo):
                repo_match = True
                break

        if not repo_match:
            continue

        if effect == "deny":
            return False, f"Denied by rule: {rule}"
        elif effect == "allow":
            has_allow = True

    if has_allow:
        return True, "Allowed"
    else:
        return False, f"No matching allow rule for {action} on {repo}"


# =============================================================================
# Parameter Branching
# =============================================================================

def resolve_param_branch(action: str, body: bytes | None) -> str:
    """
    Resolve _PARAM_BRANCH marked actions based on request body.
    """
    if "_PARAM_BRANCH" not in action:
        return action

    body_json = {}
    if body:
        try:
            body_json = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    if action == "pr:create_PARAM_BRANCH":
        if body_json.get("draft", False):
            return "pr:create_draft"
        return "pr:create"

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

    if action == "pr:merge_PARAM_BRANCH":
        merge_method = body_json.get("merge_method", "merge")
        if merge_method == "squash":
            return "pr:merge_squash"
        if merge_method == "rebase":
            return "pr:merge_rebase"
        return "pr:merge_commit"

    if action == "pr:review_PARAM_BRANCH":
        event = body_json.get("event", "").upper()
        if event == "APPROVE":
            return "pr:approve"
        if event == "REQUEST_CHANGES":
            return "pr:request_changes"
        if event == "COMMENT":
            return "pr:review_comment_only"
        return "pr:review_pending"

    if action == "pr:review_submit_PARAM_BRANCH":
        event = body_json.get("event", "").upper()
        if event == "APPROVE":
            return "pr:review_submit_approve"
        if event == "REQUEST_CHANGES":
            return "pr:review_submit_request_changes"
        return "pr:review_submit_comment"

    return action.replace("_PARAM_BRANCH", "")


# =============================================================================
# Endpoint Matching
# =============================================================================

def match_endpoint(method: str, path: str) -> tuple[str | None, dict]:
    """Match REST API endpoint to action."""
    for allowed_method, pattern, action in ENDPOINT_ACTIONS:
        if method != allowed_method:
            continue
        match = re.match(pattern, path)
        if match:
            return action, match.groupdict()
    return None, {}


def match_git_endpoint(method: str, path: str, query: str) -> tuple[str | None, dict]:
    """Match git smart HTTP endpoint to action."""
    for allowed_method, pattern, action in GIT_ENDPOINT_ACTIONS:
        if method != allowed_method:
            continue
        match = re.match(pattern, path)
        if match:
            if path.endswith("/info/refs"):
                if "service=git-receive-pack" in query:
                    return "git:write", match.groupdict()
                else:
                    return "git:read", match.groupdict()
            return action, match.groupdict()
    return None, {}


# =============================================================================
# PAT Selection
# =============================================================================

def select_pat(repo: str, config: dict) -> str:
    """Select appropriate PAT for repository."""
    for fg_pat in config.get("fine_grained_pats", []):
        for repo_pattern in fg_pat.get("repos", []):
            if expand_repo_pattern(repo_pattern, repo):
                return fg_pat["pat"]
    return config["classic_pat"]


# =============================================================================
# Config Loading
# =============================================================================

def load_config(config_path: Path) -> dict:
    """Load and validate config file."""
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        print(f"\nCreate the config file with:", file=sys.stderr)
        print(f"  mkdir -p {config_path.parent}", file=sys.stderr)
        print(f"  cat > {config_path} << 'EOF'", file=sys.stderr)
        print("""{
  "classic_pat": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "fine_grained_pats": [
    { "pat": "github_pat_xxx", "repos": ["owner/*"] }
  ],
  "rules": [
    { "effect": "allow", "actions": ["*"], "repos": ["owner/repo"] },
    { "effect": "deny", "actions": ["pr:merge_*"], "repos": ["*"] }
  ]
}
EOF""", file=sys.stderr)
        sys.exit(1)

    stat_info = config_path.stat()
    if stat_info.st_mode & 0o077:
        print(f"Error: Config file has insecure permissions: {oct(stat_info.st_mode)[-3:]}", file=sys.stderr)
        print(f"Run: chmod 600 {config_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(config_path) as f:
            config = json5.load(f)
    except ValueError as e:
        print(f"Error: Invalid JSON5 in config file: {e}", file=sys.stderr)
        sys.exit(1)

    if "classic_pat" not in config:
        print("Error: Missing required field: classic_pat", file=sys.stderr)
        sys.exit(1)

    if "rules" not in config:
        print("Error: Missing required field: rules", file=sys.stderr)
        sys.exit(1)

    if not isinstance(config["rules"], list) or len(config["rules"]) == 0:
        print("Error: rules must be a non-empty list", file=sys.stderr)
        sys.exit(1)

    if "fine_grained_pats" in config:
        if not isinstance(config["fine_grained_pats"], list):
            print("Error: fine_grained_pats must be a list", file=sys.stderr)
            sys.exit(1)
        for i, fg_pat in enumerate(config["fine_grained_pats"]):
            if "pat" not in fg_pat:
                print(f"Error: fine_grained_pats[{i}] missing 'pat'", file=sys.stderr)
                sys.exit(1)
            if "repos" not in fg_pat or not isinstance(fg_pat["repos"], list):
                print(f"Error: fine_grained_pats[{i}] missing or invalid 'repos'", file=sys.stderr)
                sys.exit(1)
    else:
        config["fine_grained_pats"] = []

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
