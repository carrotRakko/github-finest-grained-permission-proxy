"""
HTTP server for fgp proxy.
"""

import argparse
from http.server import HTTPServer
from pathlib import Path

from .core.policy import (
    load_config,
    ACTION_CATEGORIES,
    DEFAULT_CONFIG_PATH,
    DEFAULT_PORT,
)
from .handler import GitHubProxyHandler


def main():
    """Run the fgp proxy server."""
    parser = argparse.ArgumentParser(description="GitHub Finest-Grained Permission Proxy")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_PATH,
        help=f"Config file path (default: {DEFAULT_CONFIG_PATH})"
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
