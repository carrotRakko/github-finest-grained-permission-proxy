"""
HTTP server for fgp proxy.
"""

import argparse
from http.server import HTTPServer
from pathlib import Path

from .core.policy import (
    load_config,
    DEFAULT_CONFIG_PATH,
    DEFAULT_PORT,
)
from .handler import GitHubProxyHandler


def mask_token(token: str) -> str:
    """Mask token for display."""
    if len(token) > 12:
        return f"{token[:4]}...{token[-4:]}"
    return "****"


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

    # Display PAT configuration
    if "pats" in config:
        print(f"\nPATs configured: {len(config['pats'])}")
        for i, pat_entry in enumerate(config["pats"]):
            masked = mask_token(pat_entry["token"])
            repos = ", ".join(pat_entry["repos"])
            print(f"  [{i}] {masked} -> {repos}")
    else:
        # Legacy format
        print(f"\nClassic PAT: {mask_token(config['classic_pat'])}")
        if config.get("fine_grained_pats"):
            print(f"Fine-grained PATs: {len(config['fine_grained_pats'])}")
            for i, fg_pat in enumerate(config["fine_grained_pats"]):
                masked = mask_token(fg_pat["pat"])
                repos = ", ".join(fg_pat["repos"])
                print(f"  [{i}] {masked} -> {repos}")

    print("\nPress Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
