"""
Discussion command module.

Provides GitHub Discussions support via GraphQL API.
gh CLI doesn't have `gh discussion` command, so this is a custom implementation.
"""

from ..core.graphql import execute_graphql, get_repository_id

# Actions this module provides
ACTIONS = [
    "discussions:read",
    "discussions:write",
]

# CLI command -> action mapping
CLI_ACTIONS = {
    "list": "discussions:read",
    "view": "discussions:read",
    "create": "discussions:write",
    "edit": "discussions:write",
    "comment": "discussions:write",
}


def get_action(subcmd: str | None, args: list[str]) -> tuple[str | None, str | None]:
    """Get action for discussion subcommand."""
    if subcmd is None:
        return None, None

    action = CLI_ACTIONS.get(subcmd)
    return (action, None) if action else (None, None)


def execute(args: list[str], owner: str, repo: str, pat: str) -> dict:
    """Execute discussion command."""
    if not args:
        raise ValueError("discussion subcommand required")

    subcmd = args[0]
    rest = args[1:]

    if subcmd == "list":
        return _list_discussions(owner, repo, pat)

    elif subcmd == "view":
        if not rest:
            raise ValueError("discussion number required")
        number = int(rest[0])
        return _view_discussion(owner, repo, number, pat)

    elif subcmd == "create":
        title, body, category = _parse_create_args(rest)
        return _create_discussion(owner, repo, title, body, category, pat)

    elif subcmd == "edit":
        if not rest:
            raise ValueError("discussion number required")
        number = int(rest[0])
        title, body = _parse_edit_args(rest[1:])
        return _update_discussion(owner, repo, number, title, body, pat)

    elif subcmd == "comment":
        return _handle_comment(rest, owner, repo, pat)

    else:
        raise ValueError(f"Unknown discussion subcommand: {subcmd}")


# =============================================================================
# Argument Parsing
# =============================================================================

def _parse_create_args(args: list[str]) -> tuple[str, str, str]:
    """Parse --title, --body, --category from args."""
    title = None
    body = None
    category = None
    i = 0
    while i < len(args):
        if args[i] in ["--title", "-t"] and i + 1 < len(args):
            title = args[i + 1]
            i += 2
        elif args[i] in ["--body", "-b"] and i + 1 < len(args):
            body = args[i + 1]
            i += 2
        elif args[i] in ["--category", "-c"] and i + 1 < len(args):
            category = args[i + 1]
            i += 2
        else:
            i += 1

    if not title:
        raise ValueError("--title is required")
    if not body:
        raise ValueError("--body is required")
    if not category:
        raise ValueError("--category is required")

    return title, body, category


def _parse_edit_args(args: list[str]) -> tuple[str | None, str | None]:
    """Parse --title, --body from args."""
    title = None
    body = None
    i = 0
    while i < len(args):
        if args[i] in ["--title", "-t"] and i + 1 < len(args):
            title = args[i + 1]
            i += 2
        elif args[i] in ["--body", "-b"] and i + 1 < len(args):
            body = args[i + 1]
            i += 2
        else:
            i += 1

    if not title and not body:
        raise ValueError("--title or --body is required")

    return title, body


def _handle_comment(args: list[str], owner: str, repo: str, pat: str) -> dict:
    """Handle comment subcommand (add or edit)."""
    if not args:
        raise ValueError("discussion number or 'edit' required")

    # Check if it's "comment edit <comment_id>"
    if args[0] == "edit":
        if len(args) < 2:
            raise ValueError("comment_id required")
        comment_id = args[1]
        body = _parse_comment_body(args[2:])
        return _update_comment(comment_id, body, pat)
    else:
        # Add comment: comment <number> --body "..."
        number = int(args[0])
        body, reply_to = _parse_add_comment_args(args[1:])
        return _add_comment(owner, repo, number, body, reply_to, pat)


def _parse_comment_body(args: list[str]) -> str:
    """Parse --body from args."""
    body = None
    i = 0
    while i < len(args):
        if args[i] in ["--body", "-b"] and i + 1 < len(args):
            body = args[i + 1]
            i += 2
        else:
            i += 1

    if not body:
        raise ValueError("--body is required")
    return body


def _parse_add_comment_args(args: list[str]) -> tuple[str, str | None]:
    """Parse --body and --reply-to from args."""
    body = None
    reply_to = None
    i = 0
    while i < len(args):
        if args[i] in ["--body", "-b"] and i + 1 < len(args):
            body = args[i + 1]
            i += 2
        elif args[i] == "--reply-to" and i + 1 < len(args):
            reply_to = args[i + 1]
            i += 2
        else:
            i += 1

    if not body:
        raise ValueError("--body is required")
    return body, reply_to


# =============================================================================
# GraphQL Operations
# =============================================================================

def _get_discussion_category_id(owner: str, repo: str, category_name: str, pat: str) -> str:
    """Get discussion category node ID."""
    query = """
    query($owner: String!, $repo: String!) {
        repository(owner: $owner, name: $repo) {
            discussionCategories(first: 100) {
                nodes {
                    id
                    name
                    slug
                }
            }
        }
    }
    """
    result = execute_graphql(query, {"owner": owner, "repo": repo}, pat)
    categories = result["data"]["repository"]["discussionCategories"]["nodes"]
    for cat in categories:
        if cat["name"].lower() == category_name.lower() or cat["slug"].lower() == category_name.lower():
            return cat["id"]
    available = [c["name"] for c in categories]
    raise ValueError(f"Category '{category_name}' not found. Available: {available}")


def _get_discussion_node_id(owner: str, repo: str, number: int, pat: str) -> str:
    """Get discussion node ID."""
    query = """
    query($owner: String!, $repo: String!, $number: Int!) {
        repository(owner: $owner, name: $repo) {
            discussion(number: $number) {
                id
            }
        }
    }
    """
    result = execute_graphql(
        query, {"owner": owner, "repo": repo, "number": number}, pat
    )
    discussion = result["data"]["repository"]["discussion"]
    if not discussion:
        raise ValueError(f"Discussion #{number} not found")
    return discussion["id"]


def _list_discussions(owner: str, repo: str, pat: str) -> dict:
    """List discussions."""
    query = """
    query($owner: String!, $repo: String!) {
        repository(owner: $owner, name: $repo) {
            discussions(first: 30, orderBy: {field: CREATED_AT, direction: DESC}) {
                nodes {
                    number
                    title
                    author { login }
                    createdAt
                    category { name }
                    comments { totalCount }
                }
            }
        }
    }
    """
    result = execute_graphql(query, {"owner": owner, "repo": repo}, pat)
    discussions = result["data"]["repository"]["discussions"]["nodes"]

    lines = []
    for d in discussions:
        author = d["author"]["login"] if d["author"] else "ghost"
        comments = d["comments"]["totalCount"]
        category = d["category"]["name"] if d["category"] else ""
        lines.append(f"#{d['number']}\t{d['title']}\t{author}\t{category}\t{comments} comments")

    return {"exit_code": 0, "stdout": "\n".join(lines), "stderr": ""}


def _view_discussion(owner: str, repo: str, number: int, pat: str) -> dict:
    """View discussion details."""
    query = """
    query($owner: String!, $repo: String!, $number: Int!) {
        repository(owner: $owner, name: $repo) {
            discussion(number: $number) {
                number
                title
                body
                author { login }
                createdAt
                category { name }
                url
                comments(first: 50) {
                    nodes {
                        id
                        author { login }
                        body
                        createdAt
                    }
                }
            }
        }
    }
    """
    result = execute_graphql(
        query, {"owner": owner, "repo": repo, "number": number}, pat
    )
    d = result["data"]["repository"]["discussion"]
    if not d:
        raise ValueError(f"Discussion #{number} not found")

    author = d["author"]["login"] if d["author"] else "ghost"
    lines = [
        f"title:\t{d['title']}",
        f"number:\t{d['number']}",
        f"author:\t{author}",
        f"category:\t{d['category']['name'] if d['category'] else ''}",
        f"url:\t{d['url']}",
        f"created:\t{d['createdAt']}",
        "",
        "--- BODY ---",
        d["body"] or "(empty)",
        "",
        "--- COMMENTS ---",
    ]
    for c in d["comments"]["nodes"]:
        c_author = c["author"]["login"] if c["author"] else "ghost"
        lines.append(f"\n[{c['id']}] {c_author} at {c['createdAt']}:")
        lines.append(c["body"])

    return {"exit_code": 0, "stdout": "\n".join(lines), "stderr": ""}


def _create_discussion(
    owner: str, repo: str, title: str, body: str, category: str, pat: str
) -> dict:
    """Create a discussion."""
    repo_id = get_repository_id(owner, repo, pat)
    category_id = _get_discussion_category_id(owner, repo, category, pat)

    mutation = """
    mutation($repositoryId: ID!, $categoryId: ID!, $title: String!, $body: String!) {
        createDiscussion(input: {repositoryId: $repositoryId, categoryId: $categoryId, title: $title, body: $body}) {
            discussion {
                number
                url
            }
        }
    }
    """
    variables = {
        "repositoryId": repo_id,
        "categoryId": category_id,
        "title": title,
        "body": body,
    }
    result = execute_graphql(mutation, variables, pat)
    d = result["data"]["createDiscussion"]["discussion"]

    return {
        "exit_code": 0,
        "stdout": d["url"],
        "stderr": f"Created discussion #{d['number']}"
    }


def _update_discussion(
    owner: str, repo: str, number: int, title: str | None, body: str | None, pat: str
) -> dict:
    """Update a discussion."""
    discussion_id = _get_discussion_node_id(owner, repo, number, pat)

    mutation = """
    mutation($discussionId: ID!, $title: String, $body: String) {
        updateDiscussion(input: {discussionId: $discussionId, title: $title, body: $body}) {
            discussion {
                number
                url
            }
        }
    }
    """
    variables = {
        "discussionId": discussion_id,
        "title": title,
        "body": body,
    }
    result = execute_graphql(mutation, variables, pat)
    d = result["data"]["updateDiscussion"]["discussion"]

    return {
        "exit_code": 0,
        "stdout": d["url"],
        "stderr": f"Updated discussion #{d['number']}"
    }


def _add_comment(
    owner: str, repo: str, number: int, body: str, reply_to: str | None, pat: str
) -> dict:
    """Add a comment to a discussion."""
    discussion_id = _get_discussion_node_id(owner, repo, number, pat)

    mutation = """
    mutation($discussionId: ID!, $body: String!, $replyToId: ID) {
        addDiscussionComment(input: {discussionId: $discussionId, body: $body, replyToId: $replyToId}) {
            comment {
                id
                url
            }
        }
    }
    """
    variables = {
        "discussionId": discussion_id,
        "body": body,
        "replyToId": reply_to,
    }
    result = execute_graphql(mutation, variables, pat)
    c = result["data"]["addDiscussionComment"]["comment"]

    return {
        "exit_code": 0,
        "stdout": c["url"],
        "stderr": f"Added comment {c['id']}"
    }


def _update_comment(comment_id: str, body: str, pat: str) -> dict:
    """Update a discussion comment."""
    mutation = """
    mutation($commentId: ID!, $body: String!) {
        updateDiscussionComment(input: {commentId: $commentId, body: $body}) {
            comment {
                id
                url
            }
        }
    }
    """
    variables = {
        "commentId": comment_id,
        "body": body,
    }
    result = execute_graphql(mutation, variables, pat)
    c = result["data"]["updateDiscussionComment"]["comment"]

    return {
        "exit_code": 0,
        "stdout": c["url"],
        "stderr": f"Updated comment {c['id']}"
    }
