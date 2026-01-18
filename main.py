#!/usr/bin/env python3
"""
GitHub Finest-Grained Permission Proxy

A proxy that provides fine-grained permission control for GitHub API access.
Classic PAT is stored on the host side, exposing only permitted operations to AI.

Features:
- GitHub REST API proxy (/repos/... etc.)
- git smart HTTP proxy (/git/{owner}/{repo}.git/... for clone/fetch/push)
- AWS IAM-style policy evaluation (allow/deny rules)

Usage:
    python main.py [--port PORT] [--config CONFIG_PATH]

Default config path: ~/.config/github-proxy/config.json
"""

from fgp.server import main

if __name__ == "__main__":
    main()
