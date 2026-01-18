"""
Sub-issue command module.

Provides GitHub Sub-Issues support via GraphQL API.
gh CLI doesn't have `gh sub-issue` command, so this is a custom implementation.
"""

from ..core.graphql import execute_graphql, get_issue_node_id

# Actions this module provides
ACTIONS = [
    "subissues:list",
    "subissues:parent",
    "subissues:add",
    "subissues:remove",
    "subissues:reprioritize",
]

# CLI command -> action mapping
CLI_ACTIONS = {
    "list": "subissues:list",
    "parent": "subissues:parent",
    "add": "subissues:add",
    "remove": "subissues:remove",
    "reorder": "subissues:reprioritize",
}


def get_action(subcmd: str | None, args: list[str]) -> tuple[str | None, str | None]:
    """Get action for sub-issue subcommand."""
    if subcmd is None:
        return None, None

    action = CLI_ACTIONS.get(subcmd)
    return (action, None) if action else (None, None)


def execute(args: list[str], owner: str, repo: str, pat: str) -> dict:
    """Execute sub-issue command."""
    if not args:
        raise ValueError("sub-issue subcommand required")

    subcmd = args[0]
    rest = args[1:]

    if subcmd == "list":
        if not rest:
            raise ValueError("issue number required")
        issue_number = int(rest[0])
        result = _list_sub_issues(owner, repo, issue_number, pat)
        lines = []
        for item in result.get("sub_issues", []):
            lines.append(f"{item['number']}\t{item['state']}\t{item['title']}")
        return {"exit_code": 0, "stdout": "\n".join(lines), "stderr": ""}

    elif subcmd == "parent":
        if not rest:
            raise ValueError("issue number required")
        issue_number = int(rest[0])
        result = _get_parent_issue(owner, repo, issue_number, pat)
        parent = result.get("parent")
        if parent:
            stdout = f"{parent['number']}\t{parent['state']}\t{parent['title']}"
        else:
            stdout = "No parent issue"
        return {"exit_code": 0, "stdout": stdout, "stderr": ""}

    elif subcmd == "add":
        if len(rest) < 2:
            raise ValueError("parent and child issue numbers required")
        parent_number = int(rest[0])
        child_number = int(rest[1])
        _add_sub_issue(owner, repo, parent_number, child_number, pat)
        return {"exit_code": 0, "stdout": f"Added #{child_number} as sub-issue of #{parent_number}", "stderr": ""}

    elif subcmd == "remove":
        if len(rest) < 2:
            raise ValueError("parent and child issue numbers required")
        parent_number = int(rest[0])
        child_number = int(rest[1])
        _remove_sub_issue(owner, repo, parent_number, child_number, pat)
        return {"exit_code": 0, "stdout": f"Removed #{child_number} from #{parent_number}", "stderr": ""}

    elif subcmd == "reorder":
        if len(rest) < 2:
            raise ValueError("parent and child issue numbers required")
        parent_number = int(rest[0])
        child_number = int(rest[1])
        before_number, after_number = _parse_reorder_args(rest[2:])
        if not before_number and not after_number:
            raise ValueError("--before or --after required")
        _reprioritize_sub_issue(owner, repo, parent_number, child_number, before_number, after_number, pat)
        return {"exit_code": 0, "stdout": "Reordered", "stderr": ""}

    else:
        raise ValueError(f"Unknown sub-issue subcommand: {subcmd}")


def _parse_reorder_args(args: list[str]) -> tuple[int | None, int | None]:
    """Parse --before and --after from args."""
    before_number = None
    after_number = None
    i = 0
    while i < len(args):
        if args[i] == "--before" and i + 1 < len(args):
            before_number = int(args[i + 1])
            i += 2
        elif args[i] == "--after" and i + 1 < len(args):
            after_number = int(args[i + 1])
            i += 2
        else:
            i += 1
    return before_number, after_number


# =============================================================================
# GraphQL Operations
# =============================================================================

def _list_sub_issues(owner: str, repo: str, issue_number: int, pat: str) -> dict:
    """List sub-issues of an issue."""
    query = """
    query($owner: String!, $repo: String!, $number: Int!) {
        repository(owner: $owner, name: $repo) {
            issue(number: $number) {
                subIssues(first: 50) {
                    nodes {
                        number
                        title
                        state
                    }
                }
            }
        }
    }
    """
    variables = {"owner": owner, "repo": repo, "number": issue_number}
    result = execute_graphql(
        query, variables, pat,
        extra_headers={"GraphQL-Features": "sub_issues"}
    )

    issue = result.get("data", {}).get("repository", {}).get("issue")
    if not issue:
        raise ValueError(f"Issue #{issue_number} not found in {owner}/{repo}")

    sub_issues = issue.get("subIssues", {}).get("nodes", [])
    return {"sub_issues": sub_issues}


def _get_parent_issue(owner: str, repo: str, issue_number: int, pat: str) -> dict:
    """Get parent issue of an issue."""
    query = """
    query($owner: String!, $repo: String!, $number: Int!) {
        repository(owner: $owner, name: $repo) {
            issue(number: $number) {
                parent {
                    number
                    title
                    state
                }
            }
        }
    }
    """
    variables = {"owner": owner, "repo": repo, "number": issue_number}
    result = execute_graphql(
        query, variables, pat,
        extra_headers={"GraphQL-Features": "sub_issues"}
    )

    issue = result.get("data", {}).get("repository", {}).get("issue")
    if not issue:
        raise ValueError(f"Issue #{issue_number} not found in {owner}/{repo}")

    parent = issue.get("parent")
    return {"parent": parent}


def _add_sub_issue(
    owner: str, repo: str, issue_number: int, sub_issue_number: int, pat: str,
    replace_parent: bool = False
) -> dict:
    """Add a sub-issue to an issue."""
    issue_id = get_issue_node_id(owner, repo, issue_number, pat)
    sub_issue_id = get_issue_node_id(owner, repo, sub_issue_number, pat)

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
    execute_graphql(
        mutation, variables, pat,
        extra_headers={"GraphQL-Features": "sub_issues"}
    )

    return {
        "success": True,
        "issue_number": issue_number,
        "sub_issue_number": sub_issue_number
    }


def _remove_sub_issue(
    owner: str, repo: str, issue_number: int, sub_issue_number: int, pat: str
) -> dict:
    """Remove a sub-issue from an issue."""
    issue_id = get_issue_node_id(owner, repo, issue_number, pat)
    sub_issue_id = get_issue_node_id(owner, repo, sub_issue_number, pat)

    mutation = """
    mutation($issueId: ID!, $subIssueId: ID!) {
        removeSubIssue(input: {issueId: $issueId, subIssueId: $subIssueId}) {
            issue { number }
            subIssue { number }
        }
    }
    """
    variables = {"issueId": issue_id, "subIssueId": sub_issue_id}
    execute_graphql(
        mutation, variables, pat,
        extra_headers={"GraphQL-Features": "sub_issues"}
    )

    return {
        "success": True,
        "issue_number": issue_number,
        "sub_issue_number": sub_issue_number
    }


def _reprioritize_sub_issue(
    owner: str, repo: str, issue_number: int, sub_issue_number: int,
    before_number: int | None, after_number: int | None, pat: str
) -> dict:
    """Reprioritize a sub-issue."""
    issue_id = get_issue_node_id(owner, repo, issue_number, pat)
    sub_issue_id = get_issue_node_id(owner, repo, sub_issue_number, pat)

    before_id = None
    after_id = None
    if before_number:
        before_id = get_issue_node_id(owner, repo, before_number, pat)
    if after_number:
        after_id = get_issue_node_id(owner, repo, after_number, pat)

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
    execute_graphql(
        mutation, variables, pat,
        extra_headers={"GraphQL-Features": "sub_issues"}
    )

    return {
        "success": True,
        "issue_number": issue_number,
        "sub_issue_number": sub_issue_number,
        "before_number": before_number,
        "after_number": after_number
    }
