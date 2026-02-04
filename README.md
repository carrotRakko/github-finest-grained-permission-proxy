# GitHub Finest-Grained Permission Proxy

> **0.x - Unstable API**: This project is in early development. The API may change without notice. Use at your own risk.

A proxy that isolates GitHub PATs from AI agents running in containers.

**Abbreviation**: `fgp`

## Background

When running AI agents (like Claude Code) in containers, storing `GH_TOKEN` as an environment variable is risky - the AI can read it via `printenv` or `/proc/self/environ`.

This proxy:
- Keeps PATs on the host side (invisible to AI)
- Selects the appropriate PAT based on repository
- Supports multiple PATs (Fine-grained + Classic)

## How It Works

```
Container (fgh CLI)
    ↓ HTTP
Host-side proxy (fgp)
    ↓ PAT selection by repo pattern
GitHub API / github.com (git)
```

## Setup

### 1. Create PATs

**Fine-grained PAT** (for your repos and orgs):
- GitHub → Settings → Developer settings → Fine-grained tokens
- Select repositories you need access to

**Classic PAT** (for collaborator repos, external orgs):
- GitHub → Settings → Developer settings → Tokens (classic)
- Required scope: `repo`

### 2. Create Config File (Host Side)

```bash
mkdir -p ~/.config/github-proxy
cat > ~/.config/github-proxy/config.json << 'EOF'
{
  "pats": [
    { "token": "github_pat_xxx", "repos": ["your-org/*"] },
    { "token": "github_pat_yyy", "repos": ["your-username/*"] },
    { "token": "ghp_zzz", "repos": ["*"] }
  ]
}
EOF
chmod 600 ~/.config/github-proxy/config.json
```

PATs are evaluated top-to-bottom. First match wins.

### 3. Start the Proxy (Host Side)

```bash
cd /path/to/github-finest-grained-permission-proxy
uv run python main.py
```

Default port: 8766

Output:
```
GitHub Proxy listening on http://0.0.0.0:8766
Config: /Users/you/.config/github-proxy/config.json

PATs configured: 3
  [0] gith...xxxx -> your-org/*
  [1] gith...yyyy -> your-username/*
  [2] ghp_...zzzz -> *

Press Ctrl+C to stop
```

## Usage (From Container)

### fgh CLI

`fgh` is a drop-in replacement for `gh` that routes through fgp.

```bash
# High-level commands (issue, pr, discussion, sub-issue)
fgh issue list -R owner/repo
fgh pr view 123 -R owner/repo
fgh sub-issue list 456 -R owner/repo
fgh discussion list -R owner/repo

# REST API (repos/owner/repo/... endpoints)
fgh api repos/owner/repo
fgh api repos/owner/repo/issues/123/timeline

# Check PAT status
fgh auth status
```

### git Operations (clone/fetch/push)

```bash
# Clone via proxy
git clone http://host.docker.internal:8766/git/owner/repo.git

# Change remote for existing repo
git remote set-url origin http://host.docker.internal:8766/git/owner/repo.git

# fetch/push work as usual
git fetch origin
git push origin feature-branch
```

## What Works

| Category | Status |
|----------|--------|
| High-level commands (issue, pr) | ✅ All work |
| REST API (fgh api) | ✅ `repos/owner/repo/...` endpoints |
| GraphQL | ❌ Blocked |
| Custom commands (sub-issue, discussion) | ✅ All work |
| git operations | ✅ clone/fetch/push |

## Repository Pattern

| Pattern | Matches |
|---------|---------|
| `owner/repo` | Exact match (case-insensitive) |
| `owner/*` | All repos of owner |
| `*` | All repos (fallback) |

## Security

- Config file requires `chmod 600`
- PATs are invisible to AI (host-side only)
- Uses HTTP proxy instead of credential helper
  - credential helper would expose PAT to container
  - HTTP proxy keeps PAT on host
- **Local network only**: This proxy has no authentication. Do not expose to the internet.

## Limitations

- **GraphQL not supported**: Use high-level commands (issue, pr, discussion, sub-issue) instead
- **Git LFS not supported**: Only basic git smart HTTP protocol (clone/fetch/push)
- **REST API limited to repos/ endpoints**: `/user`, `/orgs/...` etc. won't work (can't determine PAT)

## Installing fgh

```bash
curl -fsSL https://raw.githubusercontent.com/carrotRakko/github-finest-grained-permission-proxy/main/install.sh | bash
```

Or copy `fgh` to your PATH manually.
