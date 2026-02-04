"""
HTTP request handler for fgp proxy.
"""

import base64
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .core.policy import (
    match_git_endpoint,
    select_pat,
)
from .commands import execute_command, COMMAND_MODULES


class GitHubProxyHandler(BaseHTTPRequestHandler):
    """GitHub API and git smart HTTP proxy handler."""

    config: dict = {}

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")

    def route_request(self, method: str):
        """Route request to appropriate handler."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/git/"):
            self.handle_git_request(method)
        elif path == "/cli":
            self.handle_cli_request(method)
        elif path == "/auth/status":
            self.handle_auth_status(method)
        else:
            self.send_error(404, f"Unknown endpoint: {path}")

    # =========================================================================
    # /auth/status endpoint
    # =========================================================================

    def handle_auth_status(self, method: str):
        """Check authentication status for all configured PATs."""
        if method != "GET":
            self.send_error(405, "Only GET is allowed")
            return

        # New format: pats array
        if "pats" in self.config:
            result = {"pats": []}
            for pat_entry in self.config["pats"]:
                status = self._check_pat_status(
                    pat_entry["token"],
                    pat_type="auto",  # Will detect from token prefix
                    repos=pat_entry.get("repos", [])
                )
                result["pats"].append(status)
        else:
            # Legacy format
            result = {
                "classic_pat": self._check_pat_status(
                    self.config["classic_pat"],
                    pat_type="classic"
                ),
                "fine_grained_pats": [],
            }
            for fg_pat in self.config.get("fine_grained_pats", []):
                status = self._check_pat_status(
                    fg_pat["pat"],
                    pat_type="fine_grained",
                    repos=fg_pat.get("repos", [])
                )
                result["fine_grained_pats"].append(status)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result, indent=2).encode("utf-8"))

    def _check_pat_status(
        self, pat: str, pat_type: str, repos: list[str] | None = None
    ) -> dict:
        """Validate a PAT by calling GitHub API /user endpoint."""
        if len(pat) > 12:
            masked = f"{pat[:4]}...{pat[-4:]}"
        else:
            masked = "****"

        try:
            req = Request(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {pat}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "fgp-proxy",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            with urlopen(req, timeout=10) as resp:
                user_data = json.loads(resp.read().decode("utf-8"))
                scopes = resp.headers.get("X-OAuth-Scopes", "")

                result = {
                    "valid": True,
                    "masked_token": masked,
                    "user": user_data.get("login"),
                    "type": pat_type,
                }

                if pat_type == "classic":
                    result["scopes"] = [s.strip() for s in scopes.split(",") if s.strip()]
                else:
                    result["repos"] = repos or []

                return result

        except HTTPError as e:
            return {
                "valid": False,
                "masked_token": masked,
                "type": pat_type,
                "error": f"HTTP {e.code}: {e.reason}",
                "repos": repos if pat_type == "fine_grained" else None,
            }
        except URLError as e:
            return {
                "valid": False,
                "masked_token": masked,
                "type": pat_type,
                "error": str(e.reason),
                "repos": repos if pat_type == "fine_grained" else None,
            }
        except Exception as e:
            return {
                "valid": False,
                "masked_token": masked,
                "type": pat_type,
                "error": str(e),
                "repos": repos if pat_type == "fine_grained" else None,
            }

    # =========================================================================
    # /cli endpoint
    # =========================================================================

    def handle_cli_request(self, method: str):
        """Handle CLI command request (for fgh)."""
        if method != "POST":
            self.send_error(405, "Only POST is allowed")
            return

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

        args = data.get("args", [])
        repo = data.get("repo")

        if not args:
            self.send_error(400, "args is required")
            return

        if not repo:
            self.send_error(400, "repo is required")
            return

        # Select PAT for this repo
        pat = select_pat(repo, self.config)
        if not pat:
            self.send_error(403, f"No PAT configured for repository: {repo}")
            return

        # Execute command
        try:
            cmd = args[0]
            owner, repo_name = repo.split("/")

            # Check if it's a custom command
            if cmd in COMMAND_MODULES:
                result = execute_command(cmd, args[1:], owner, repo_name, pat)
            else:
                # Standard gh command via subprocess
                result = self.execute_gh_cli(args, repo, pat)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))

        except ValueError as e:
            self.send_error(400, str(e))
        except Exception as e:
            self.send_error(500, str(e))

    def execute_gh_cli(self, args: list[str], repo: str, pat: str) -> dict:
        """Execute standard gh command via subprocess."""
        gh_args = ["gh"] + args + ["-R", repo]

        result = subprocess.run(
            gh_args,
            capture_output=True,
            text=True,
            timeout=60,
            env={
                **os.environ,
                "GH_TOKEN": pat,
                "GH_HOST": "github.com",
                "GH_FORCE_TTY": "1",
                "NO_COLOR": "1",
            }
        )

        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    # =========================================================================
    # /git/* endpoint
    # =========================================================================

    def handle_git_request(self, method: str):
        """Handle git smart HTTP protocol request."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parsed.query

        _, groups = match_git_endpoint(method, path, query)

        owner = groups.get("owner")
        repo = groups.get("repo")
        if not owner or not repo:
            self.send_error(400, "Could not determine repository from git path")
            return

        full_repo = f"{owner}/{repo}"

        # Select PAT for this repo
        pat = select_pat(full_repo, self.config)
        if not pat:
            self.send_error(403, f"No PAT configured for repository: {full_repo}")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        try:
            response_data, response_headers, status_code = self.proxy_git_to_github(
                method, owner, repo, path, query, body, pat
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
        self, method: str, owner: str, repo: str, path: str, query: str, body: bytes | None, pat: str
    ) -> tuple[bytes, dict, int]:
        """Proxy git smart HTTP to GitHub."""
        git_path = path.replace(f"/git/{owner}/{repo}.git", f"/{owner}/{repo}.git")
        url = f"https://github.com{git_path}"
        if query:
            url += f"?{query}"

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

    # =========================================================================
    # HTTP method handlers
    # =========================================================================

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
        """CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
