# GitHub Finest-Grained Permission Proxy

> **0.x - Unstable API**: This project is in early development. The API may change without notice. Use at your own risk.

GitHub API および git smart HTTP protocol への権限制限付きプロキシ。
AI エージェントに Classic PAT の一部権限だけを公開する。

**略称**: `fgp-proxy`

## 背景

Fine-grained PAT は他ユーザーのリポジトリ（collaborator として参加しているもの）にはアクセスできない。
Classic PAT ならアクセスできるが、全リポジトリに Full Access になってしまう。

このプロキシは:
- Classic PAT をホスト側に置く（AI からは見えない）
- AWS IAM 式のポリシーで許可/拒否を細かく制御
- GitHub API と git 操作（clone/fetch/push）の両方をカバー

## 仕組み

```
DevContainer (Claude Code)
    ↓ HTTP
ホスト側プロキシ (このツール)
    ↓ ポリシー評価 → Classic PAT 付与
GitHub API / github.com (git)
```

## セットアップ

### 1. Classic PAT の発行

GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)

必要なスコープ:
- `repo` (Full control of private repositories)

### 2. 設定ファイルを作成（ホスト側）

```fish
mkdir -p ~/.config/github-proxy
cat > ~/.config/github-proxy/config.json << 'EOF'
{
  "classic_pat": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "rules": [
    { "effect": "allow", "actions": ["*"], "repos": ["alice/private-repo"] },
    { "effect": "allow", "actions": ["metadata:read", "code:*", "git:*"], "repos": ["bob/side-project"] },
    { "effect": "deny", "actions": ["pulls:merge"], "repos": ["*"] }
  ]
}
EOF
chmod 600 ~/.config/github-proxy/config.json
```

## ポリシー評価（AWS IAM 式）

評価ロジック:
1. デフォルト: 暗黙の Deny
2. 一つでも Deny にマッチ → 即拒否（**Deny always wins**）
3. 一つでも Allow にマッチ → 許可
4. 何もマッチしない → 拒否

### ルール形式

```json
{
  "effect": "allow" | "deny",
  "actions": ["action:operation", ...],
  "repos": ["owner/repo", ...]
}
```

### アクション体系（層1/層2）

PR 関連は細かい粒度（層1）と便利セット（層2 Bundle）の両方で設定できる。

**層2 Bundle（便利セット）**:

| Bundle | 説明 |
|--------|------|
| `pull-requests:read` | PR 読み取り（公式 Fine-grained PAT 互換） |
| `pull-requests:write` | PR 読み取り + 書き込み全部（公式 Fine-grained PAT 互換） |
| `pulls:contribute` | PR 読み取り + 貢献系（作成、コメント、レビュー）、close/delete/merge は含まない |

**層1 Action（細かい粒度）**:

| カテゴリ | アクション例 | 説明 |
|----------|-------------|------|
| pr (read) | `pr:list`, `pr:get`, `pr:commits`, `pr:files` | PR 読み取り |
| pr (write) | `pr:create`, `pr:update`, `pr:comment_create`, `pr:approve` | PR 書き込み |
| pr (merge) | `pr:merge_commit`, `pr:merge_squash`, `pr:merge_rebase` | PR マージ |
| pr (admin) | `pr:close`, `pr:reopen`, `pr:comment_delete`, `pr:review_dismiss` | PR 管理 |

詳細は [specs/pr.md](specs/pr.md) を参照。

**その他のアクション**:

| カテゴリ | アクション | 説明 |
|----------|-----------|------|
| metadata | `metadata:read` | リポジトリ情報、ブランチ、タグ等 |
| actions | `actions:read` | GitHub Actions のワークフロー、実行結果 |
| statuses | `statuses:read` | コミットステータス、チェック結果 |
| code | `code:read`, `code:write` | ファイル内容、git refs 等 |
| issues | `issues:read`, `issues:write` | Issue 操作 |
| git | `git:read`, `git:write` | git clone/fetch/push |

### ワイルドカード

| パターン | 展開 |
|----------|------|
| `*` | 全アクション |
| `issues:*` | `issues:read`, `issues:write` |
| `pr:*` | 全 PR 層1 action |

### リポジトリパターン

| パターン | マッチ |
|----------|--------|
| `owner/repo` | 完全一致（case-insensitive） |
| `owner/*` | owner の全リポジトリ |
| `*` | 全リポジトリ |

## 起動（ホスト側で実行）

```bash
cd /path/to/detective-report-agent
python tools/github-proxy/main.py
```

デフォルトポート: 8766

起動時にポリシールールが表示される:
```
GitHub Proxy listening on http://0.0.0.0:8766
Config: /Users/you/.config/github-proxy/config.json

Policy rules: 3
  [0] ALLOW: * on alice/private-repo
  [1] ALLOW: metadata:read, code:*, git:* on bob/side-project
  [2] DENY: pulls:merge on *

Available actions:
  metadata: read
  actions: read
  statuses: read
  code: read, write
  issues: read, write
  pulls: read, contribute, merge
  git: read, write

Endpoints: 38 API + 3 git
```

## 使い方（DevContainer から）

### GitHub API

```bash
# リポジトリ情報取得
curl http://host.docker.internal:8766/repos/alice/private-repo

# Issue 一覧
curl http://host.docker.internal:8766/repos/alice/private-repo/issues

# PR 作成
curl -X POST http://host.docker.internal:8766/repos/alice/private-repo/pulls \
  -H "Content-Type: application/json" \
  -d '{"title": "Test PR", "head": "feature-branch", "base": "main"}'
```

### git 操作（clone/fetch/push）

```bash
# clone（プロキシ経由）
git clone http://host.docker.internal:8766/git/alice/private-repo.git

# 既存リポジトリの remote を変更
git remote set-url origin http://host.docker.internal:8766/git/alice/private-repo.git

# fetch/push は通常通り
git fetch origin
git push origin feature-branch
```

## 設定例

### 読み取り専用

```json
{
  "rules": [
    { "effect": "allow", "actions": ["metadata:read", "code:read", "issues:read", "pull-requests:read"], "repos": ["*"] }
  ]
}
```

### AI エージェント向け（PR 貢献は許可、merge/close は禁止）

```json
{
  "rules": [
    { "effect": "allow", "actions": ["pulls:contribute", "code:*", "git:*"], "repos": ["owner/repo"] }
  ]
}
```

`pulls:contribute` は PR 作成・コメント・レビューを許可するが、merge/close/delete は含まない。

### 層1 action で細かく制御

```json
{
  "rules": [
    { "effect": "allow", "actions": ["pull-requests:read", "pr:create", "pr:comment_create"], "repos": ["owner/repo"] },
    { "effect": "deny", "actions": ["pr:approve", "pr:request_changes"], "repos": ["*"] }
  ]
}
```

PR 作成とコメントは許可、approve/request_changes は禁止。

### リポジトリごとに権限を分ける

```json
{
  "rules": [
    { "effect": "allow", "actions": ["*"], "repos": ["my-org/main-repo"] },
    { "effect": "allow", "actions": ["metadata:read", "pull-requests:read"], "repos": ["my-org/other-repo"] },
    { "effect": "deny", "actions": ["pr:merge_commit", "pr:merge_squash", "pr:merge_rebase"], "repos": ["*"] }
  ]
}
```

## セキュリティ

- 設定ファイルは `chmod 600` 必須
- Classic PAT は AI から見えない（ホスト側のみ）
- ポリシーにマッチしないリクエストは 403
- git credential helper 方式ではなく HTTP プロキシ方式を採用
  - credential helper だと PAT が DevContainer に入ってしまう
  - HTTP プロキシなら PAT はホスト側に留まる
- **ローカルネットワーク専用**: このプロキシは認証なしで動作するため、インターネットに公開してはいけない

## 制限事項

- **Git LFS 非対応**: git smart HTTP protocol の基本操作（clone/fetch/push）のみ対応
- **GitHub API のページネーション**: プロキシはレスポンスをそのまま転送するため、クライアント側で処理が必要
