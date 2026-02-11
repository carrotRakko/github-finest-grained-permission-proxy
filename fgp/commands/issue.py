"""
Issue command module.

Provides partial body replacement for Issues and Issue comments via REST API.
Most issue subcommands fall through to gh CLI (returns None).
"""

import json
from urllib.request import Request, urlopen

# Actions this module provides
ACTIONS = [
    "issues:edit",
    "issues:comment_edit",
]

# CLI command -> action mapping
CLI_ACTIONS = {
    "edit": "issues:edit",
    "comment_edit": "issues:comment_edit",
}


def get_action(subcmd: str | None, args: list[str]) -> tuple[str | None, str | None]:
    """Get action for issue subcommand."""
    if subcmd == "edit" and _has_old_and_new(args):
        return "issues:edit", None
    if subcmd == "comment" and len(args) > 0 and args[0] == "edit":
        if _has_old_and_new(args[1:]):
            return "issues:comment_edit", None
    return None, None


def execute(args: list[str], owner: str, repo: str, pat: str) -> dict | None:
    """
    Execute issue command.

    Returns None to fall through to gh CLI for unhandled subcommands.
    """
    if not args:
        return None

    subcmd = args[0]
    rest = args[1:]

    if subcmd == "edit" and _has_old_and_new(rest):
        return _handle_edit(rest, owner, repo, pat)

    if subcmd == "comment" and len(rest) > 0 and rest[0] == "edit":
        if _has_old_and_new(rest[1:]):
            return _handle_comment_edit(rest[1:], owner, repo, pat)

    return None  # Fall through to gh CLI


# =============================================================================
# Argument parsing
# =============================================================================

def _has_old_and_new(args: list[str]) -> bool:
    """Check if both --old and --new are present."""
    has_old = any(a == "--old" for a in args)
    has_new = any(a == "--new" for a in args)
    return has_old and has_new


def _parse_edit_args(args: list[str]) -> tuple[list[str], str, str, bool]:
    """
    Parse --old, --new, --replace-all from args.

    Returns (positional_args, old, new, replace_all).
    Raises ValueError if --old or --new value is missing.
    """
    positional = []
    old = None
    new = None
    replace_all = False

    i = 0
    while i < len(args):
        if args[i] == "--old":
            if i + 1 >= len(args):
                raise ValueError("--old requires a value")
            old = args[i + 1]
            i += 2
        elif args[i] == "--new":
            if i + 1 >= len(args):
                raise ValueError("--new requires a value")
            new = args[i + 1]
            i += 2
        elif args[i] == "--replace-all":
            replace_all = True
            i += 1
        else:
            positional.append(args[i])
            i += 1

    return positional, old, new, replace_all


# =============================================================================
# Partial replacement logic
# =============================================================================

def _partial_replace(body: str, old: str, new: str, replace_all: bool) -> str:
    """
    Replace old with new in body.

    Same semantics as Claude Code's Edit tool:
    - Fail if old not found
    - Fail if old matches multiple locations (unless --replace-all)
    """
    count = body.count(old)

    if count == 0:
        raise ValueError("old string not found in body")

    if count > 1 and not replace_all:
        raise ValueError(
            f"old string found {count} times in body "
            f"(use --replace-all to replace all occurrences)"
        )

    if replace_all:
        return body.replace(old, new)
    else:
        return body.replace(old, new, 1)


# =============================================================================
# GitHub REST API
# =============================================================================

def _github_rest(method: str, url: str, pat: str, body: dict | None = None) -> dict:
    """Execute GitHub REST API request."""
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "fgp-proxy/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    req = Request(url, data=data, headers=headers, method=method)

    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


# =============================================================================
# Command handlers
# =============================================================================

def _handle_edit(args: list[str], owner: str, repo: str, pat: str) -> dict:
    """Handle `issue edit <number> --old "..." --new "..."`."""
    positional, old, new, replace_all = _parse_edit_args(args)

    if not positional:
        raise ValueError("issue number required")

    issue_number = int(positional[0])

    # GET current body
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    issue_data = _github_rest("GET", url, pat)
    current_body = issue_data.get("body") or ""

    # Partial replace
    updated_body = _partial_replace(current_body, old, new, replace_all)

    # PATCH
    _github_rest("PATCH", url, pat, body={"body": updated_body})

    return {
        "exit_code": 0,
        "stdout": "",
        "stderr": f"Updated issue #{issue_number}",
    }


def _handle_comment_edit(args: list[str], owner: str, repo: str, pat: str) -> dict:
    """Handle `issue comment edit <comment-id> --old "..." --new "..."`."""
    positional, old, new, replace_all = _parse_edit_args(args)

    if not positional:
        raise ValueError("comment ID required")

    comment_id = positional[0]

    # GET current body
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{comment_id}"
    comment_data = _github_rest("GET", url, pat)
    current_body = comment_data.get("body") or ""

    # Partial replace
    updated_body = _partial_replace(current_body, old, new, replace_all)

    # PATCH
    _github_rest("PATCH", url, pat, body={"body": updated_body})

    return {
        "exit_code": 0,
        "stdout": "",
        "stderr": f"Updated comment {comment_id}",
    }
