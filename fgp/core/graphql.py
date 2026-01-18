"""
GraphQL execution utilities.
"""

import json
from urllib.request import Request, urlopen


def execute_graphql(
    query: str,
    variables: dict,
    pat: str,
    extra_headers: dict | None = None
) -> dict:
    """
    Execute a GraphQL query against GitHub API.

    Args:
        query: GraphQL query or mutation string
        variables: Variables for the query
        pat: Personal access token
        extra_headers: Additional headers (e.g., GraphQL-Features)

    Returns:
        Response data dict

    Raises:
        ValueError: If GraphQL returns errors
    """
    url = "https://api.github.com/graphql"

    body = {"query": query}
    if variables:
        body["variables"] = variables

    headers = {
        "Authorization": f"bearer {pat}",
        "Content-Type": "application/json",
        "User-Agent": "fgp-proxy/1.0",
    }

    if extra_headers:
        headers.update(extra_headers)

    req = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    with urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
        if "errors" in result:
            raise ValueError(f"GraphQL error: {result['errors']}")
        return result


def get_repository_id(owner: str, repo: str, pat: str) -> str:
    """Get repository node ID."""
    query = """
    query($owner: String!, $repo: String!) {
        repository(owner: $owner, name: $repo) {
            id
        }
    }
    """
    result = execute_graphql(query, {"owner": owner, "repo": repo}, pat)
    return result["data"]["repository"]["id"]


def get_issue_node_id(owner: str, repo: str, issue_number: int, pat: str) -> str:
    """Get issue node ID."""
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
    result = execute_graphql(
        query, variables, pat,
        extra_headers={"GraphQL-Features": "sub_issues"}
    )

    issue = result.get("data", {}).get("repository", {}).get("issue")
    if not issue:
        raise ValueError(f"Issue #{issue_number} not found in {owner}/{repo}")
    return issue["id"]
