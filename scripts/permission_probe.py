#!/usr/bin/env python3
"""
GitHub GraphQL Permission Probe

Fine-grained PAT の権限で、どの Repository フィールドにアクセスできるかを調査する。
PAT を変えて実行すれば、異なる権限での結果を比較できる。

Usage:
    GH_TOKEN=xxx python scripts/permission_probe.py --repo owner/repo

    # または gh auth で認証済みなら
    python scripts/permission_probe.py --repo owner/repo
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


def run_graphql_query(query: str) -> dict[str, Any]:
    """gh api graphql を使ってクエリを実行"""
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}"],
        capture_output=True,
        text=True,
    )

    try:
        return json.loads(result.stdout or result.stderr)
    except json.JSONDecodeError:
        return {"raw_error": result.stderr, "raw_stdout": result.stdout}


def get_repository_fields() -> list[dict[str, Any]]:
    """Repository タイプの全フィールドを introspection で取得"""
    query = """
    {
      __type(name: "Repository") {
        fields {
          name
          description
          args {
            name
            type {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
          type {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
        }
      }
    }
    """
    result = run_graphql_query(query)
    return result.get("data", {}).get("__type", {}).get("fields", [])


def has_required_args(field: dict[str, Any]) -> bool:
    """フィールドに必須引数があるかどうか"""
    for arg in field.get("args", []):
        arg_type = arg.get("type", {})
        if arg_type.get("kind") == "NON_NULL":
            return True
    return False


def get_type_name(field_type: dict[str, Any]) -> str:
    """フィールドの型名を取得"""
    if field_type.get("name"):
        return field_type["name"]
    if field_type.get("ofType"):
        return get_type_name(field_type["ofType"])
    return ""


def get_type_kind(field_type: dict[str, Any]) -> str:
    """フィールドの型の kind を取得 (NON_NULL, LIST を剥がす)"""
    kind = field_type.get("kind")
    if kind in ("NON_NULL", "LIST") and field_type.get("ofType"):
        return get_type_kind(field_type["ofType"])
    return kind or ""


# 必須引数があるフィールドの手動指定
# (field_name, query_fragment)
MANUAL_FIELDS = [
    ("discussion", "discussion(number: 518) { title }"),
    ("issue", "issue(number: 1) { title }"),
    ("pullRequest", "pullRequest(number: 1) { title }"),
    ("ref", 'ref(qualifiedName: "refs/heads/main") { name }'),
    ("refs", 'refs(first: 1, refPrefix: "refs/heads/") { nodes { name } }'),
    ("label", 'label(name: "bug") { name }'),
    ("milestone", "milestone(number: 1) { title }"),
    ("environment", 'environment(name: "dev") { name }'),
    ("release", "release(tagName: \"v1.0.0\") { name }"),
    ("vulnerabilityAlert", "vulnerabilityAlert(number: 1) { id }"),
    ("discussionCategory", 'discussionCategory(slug: "general") { name }'),
    ("issueOrPullRequest", "issueOrPullRequest(number: 1) { __typename }"),
    ("projectV2", "projectV2(number: 1) { title }"),
    ("ruleset", "ruleset(databaseId: 1) { name }"),
    ("issueType", 'issueType(name: "bug") { name }'),
    ("repositoryCustomPropertyValue", 'repositoryCustomPropertyValue(name: "test") { name }'),
    ("suggestedActors", 'suggestedActors(first: 1, capabilities: [CAN_BE_ASSIGNED]) { nodes { login } }'),
]


# 特定の型に対するサブフィールド選択
TYPE_SELECTIONS = {
    # Interface 型
    "RepositoryOwner": "login",
    "Actor": "login",
    "Node": "__typename",
    "GitObject": "oid",
    "Closable": "closed",
    "Assignable": "__typename",
    "ProfileOwner": "login",

    # よくある Object 型
    "IssueTemplate": "name",
    "PullRequestTemplate": "filename",
    "RepositoryCodeowners": "errors { path }",
    "RepositoryContactLink": "about",
    "ContributingGuidelines": "body",
    "FundingLink": "platform",
    "RepositoryInteractionAbility": "expiresAt",
    "RepositoryPlanFeatures": "maximumAssignees",
    "Submodule": "name",
    "RepositoryCustomPropertyValue": "name",
    "License": "name",
    "CodeOfConduct": "name",
    "Ref": "name",
    "Release": "name",
    "Language": "name",
    "RepositoryTopic": "topic { name }",
    "Milestone": "title",
    "Label": "name",
    "DeployKey": "title",
    "Environment": "name",
    "BranchProtectionRule": "pattern",
    "Deployment": "environment",
    "PinnedDiscussion": "discussion { title }",
    "PinnedIssue": "issue { title }",
    "PackageConnection": "nodes { name }",
    "RepositoryVulnerabilityAlert": "securityVulnerability { package { name } }",
    "SecurityAdvisory": "summary",
}


def build_query_fragment(field: dict[str, Any]) -> str | None:
    """フィールドに対するクエリフラグメントを生成"""
    name = field["name"]
    field_type = field.get("type", {})

    if has_required_args(field):
        return None

    type_name = get_type_name(field_type)
    type_kind = get_type_kind(field_type)

    # Connection 型
    if type_name.endswith("Connection"):
        inner_type = type_name.replace("Connection", "")
        selection = TYPE_SELECTIONS.get(inner_type, "id")
        # id がないかもしれないので __typename も試す
        if selection == "id":
            selection = "__typename"
        return f"{name}(first: 1) {{ nodes {{ {selection} }} }}"

    # スカラー型
    if type_kind == "SCALAR" or type_kind == "ENUM":
        return name

    # リスト型 (Connection じゃない)
    if field_type.get("kind") == "LIST" or (
        field_type.get("kind") == "NON_NULL" and
        field_type.get("ofType", {}).get("kind") == "LIST"
    ):
        selection = TYPE_SELECTIONS.get(type_name, "__typename")
        return f"{name} {{ {selection} }}"

    # Object/Interface 型
    if type_kind in ("OBJECT", "INTERFACE", "UNION"):
        selection = TYPE_SELECTIONS.get(type_name, "__typename")
        return f"{name} {{ {selection} }}"

    # その他
    return name


def probe_field(owner: str, repo: str, field_name: str, query_fragment: str) -> dict[str, Any]:
    """特定のフィールドにアクセスできるか調査"""
    query = f"""
    query {{
      repository(owner: "{owner}", name: "{repo}") {{
        {query_fragment}
      }}
    }}
    """

    result = run_graphql_query(query)

    # 結果を解析
    if "errors" in result:
        errors = result["errors"]
        forbidden = any(e.get("type") == "FORBIDDEN" for e in errors)
        undefined = any(e.get("extensions", {}).get("code") == "undefinedField" for e in errors)

        # エラーがあっても部分的にデータが取れる場合がある
        data = result.get("data", {}).get("repository")
        if data is not None and field_name in data and data[field_name] is not None:
            return {
                "accessible": True,
                "partial_error": True,
            }

        if forbidden:
            return {
                "accessible": False,
                "reason": "forbidden",
                "error": errors[0].get("message", "")[:100],
            }

        # クエリ構文エラー等
        return {
            "accessible": True,  # 権限的には OK、クエリの書き方の問題
            "query_error": True,
            "error": errors[0].get("message", "")[:100],
        }

    # データが取れたか
    data = result.get("data", {}).get("repository")
    if data is None:
        return {
            "accessible": False,
            "reason": "forbidden",
            "error": "repository is null",
        }

    return {
        "accessible": True,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Probe GitHub GraphQL permissions")
    parser.add_argument("--repo", required=True, help="Repository in owner/repo format")
    parser.add_argument("--output", "-o", help="Output JSON file (default: stdout)")
    parser.add_argument("--note", help="Note about the PAT permissions (for documentation)")

    args = parser.parse_args()

    owner, repo = args.repo.split("/")

    print("Fetching Repository schema via introspection...", file=sys.stderr)
    all_fields = get_repository_fields()
    print(f"Found {len(all_fields)} fields", file=sys.stderr)

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repository": args.repo,
        "pat_note": args.note or "Not specified - add --note to document PAT permissions",
        "total_fields": len(all_fields),
        "fields": {},
        "skipped_fields": [],
    }

    # 手動フィールドの名前セット
    manual_field_names = {name for name, _ in MANUAL_FIELDS}

    probed = 0
    for field in all_fields:
        field_name = field["name"]

        # 手動指定があるフィールドは後で処理
        if field_name in manual_field_names:
            continue

        query_fragment = build_query_fragment(field)

        if query_fragment is None:
            results["skipped_fields"].append({
                "name": field_name,
                "reason": "has required arguments (no manual override)",
            })
            continue

        probed += 1
        print(f"  [{probed}] {field_name}...", file=sys.stderr, end=" ", flush=True)

        try:
            result = probe_field(owner, repo, field_name, query_fragment)
            results["fields"][field_name] = result

            if result.get("accessible"):
                if result.get("query_error"):
                    print("~ (query error, but not forbidden)", file=sys.stderr)
                else:
                    print("✓", file=sys.stderr)
            else:
                print("✗ FORBIDDEN", file=sys.stderr)
        except Exception as e:
            results["fields"][field_name] = {
                "accessible": False,
                "reason": "exception",
                "error": str(e),
            }
            print(f"ERROR: {e}", file=sys.stderr)

    # 手動指定フィールドを処理
    print("\n  [Manual fields]", file=sys.stderr)
    for field_name, query_fragment in MANUAL_FIELDS:
        probed += 1
        print(f"  [{probed}] {field_name}...", file=sys.stderr, end=" ", flush=True)

        try:
            result = probe_field(owner, repo, field_name, query_fragment)
            results["fields"][field_name] = result

            if result.get("accessible"):
                if result.get("query_error"):
                    print("~ (query error, but not forbidden)", file=sys.stderr)
                else:
                    print("✓", file=sys.stderr)
            else:
                print("✗ FORBIDDEN", file=sys.stderr)
        except Exception as e:
            results["fields"][field_name] = {
                "accessible": False,
                "reason": "exception",
                "error": str(e),
            }
            print(f"ERROR: {e}", file=sys.stderr)

    # 結果を出力
    output_json = json.dumps(results, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)
        print(f"\nResults written to {args.output}", file=sys.stderr)
    else:
        print(output_json)

    # サマリー
    accessible = sum(1 for r in results["fields"].values() if r.get("accessible"))
    forbidden = sum(1 for r in results["fields"].values() if r.get("reason") == "forbidden")
    query_errors = sum(1 for r in results["fields"].values() if r.get("query_error"))
    total = len(results["fields"])
    skipped = len(results["skipped_fields"])

    print(f"\nSummary:", file=sys.stderr)
    print(f"  Total fields in schema: {len(all_fields)}", file=sys.stderr)
    print(f"  Probed: {total}", file=sys.stderr)
    print(f"  Skipped (require args): {skipped}", file=sys.stderr)
    print(f"  Accessible: {accessible}", file=sys.stderr)
    print(f"  FORBIDDEN: {forbidden}", file=sys.stderr)
    print(f"  Query errors (not forbidden): {query_errors}", file=sys.stderr)


if __name__ == "__main__":
    main()
