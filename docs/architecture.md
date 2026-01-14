# fgh / fgp アーキテクチャ

## 背景

### fine-grained PAT の制約

fine-grained PAT は以下の repo にしか発行できない：
- 自分が所属している org の repo
- 自分が owner の repo

以下は fine-grained PAT では対応できない：
- 自分が所属していない org の repo（例: anthropic/claude-code に issue 投稿）
- collaborator として招待されただけの repo

→ これらは **classic PAT** が必要
→ でも classic PAT は権限が広すぎて AI に直接渡したくない
→ **fgp（プロキシ）** が間に入って許可された操作だけ通す

---

## コンポーネント

```
ユーザー(AI) ---(1)---> fgh ---(2)---> fgp ---(3)---> GitHub
                         |
                         +---(4)---> gh ---(5)---> GitHub
```

| コンポーネント | どこで動く | 役割 |
|---------------|-----------|------|
| **fgh** | devcontainer | CLI。ルーター。プロキシ対象か判定して振り分ける |
| **fgp** | ホスト | HTTP プロキシ。classic PAT を持ち、許可された操作だけ通す |
| **gh** | devcontainer | GitHub 公式 CLI。fine-grained PAT で認証済み |

---

## fgh の責任

**シンプルなルーターに徹する**

```
fgh の判定:
1. プロキシ対象 repo か？（fgp の /proxy-repos で取得）
2. 対象 → fgp にパススルー
3. 対象外 → gh にパススルー（カスタムコマンドは砕いて gh へ）
```

---

## 矢印の整理

### (1) ユーザー → fgh

CLI コマンド:
```bash
fgh issue list
fgh api /repos/owner/repo/issues
fgh api graphql -f query='...'
fgh subissue add 123 456  # カスタム
```

### (2) fgh → fgp（プロキシ対象の場合）

**CLI 形式を HTTP で送る**:
```
POST /cli
{
  "args": ["issue", "list", "--label", "bug"],
  "repo": "owner/repo"
}
```

### (3) fgp → GitHub

- ポリシー評価（allow/deny）
- 許可されたら GitHub API を叩く（classic PAT で認証）

### (4) fgh → gh（プロキシ対象外の場合）

gh にそのままパススルー:
```bash
gh issue list
gh api /repos/owner/repo/issues
gh api graphql -f query='...'
```

カスタムコマンドは砕いて gh に送る:
```bash
# fgh subissue add 123 456
# ↓ 砕いて
gh api graphql ...  # node ID 取得
gh api graphql ...  # node ID 取得
gh api graphql ...  # addSubIssue mutation
```

### (5) gh → GitHub

REST API または GraphQL API（fine-grained PAT で認証）

---

## コマンド種別と処理フロー

| 種別 | 例 | プロキシ対象 | プロキシ対象外 |
|-----|-----|------------|--------------|
| 高レベル | `fgh issue list` | fgp `/cli` | gh パススルー |
| REST | `fgh api /repos/...` | fgp `/cli` | gh パススルー |
| GraphQL | `fgh api graphql ...` | fgp `/cli` | gh パススルー |
| カスタム | `fgh subissue add ...` | fgp `/cli` | 砕いて gh |

---

## fgp の責任

1. `/proxy-repos` - プロキシ対象 repo 一覧を返す
2. `/cli` - CLI コマンドを受け取り、GitHub API を叩く
3. ポリシー評価 - allow/deny ルールに基づいてアクセス制御
4. REST API プロキシ - `/repos/...` 等を GitHub に中継（従来互換）
5. カスタム操作 - sub-issues 等は `/cli` 経由で `gh api graphql` として実行

---

## 実装状況

- [x] `/cli` エンドポイント（fgp）
- [ ] `/cli` での高レベルコマンド → action マッピング（cli_args_to_action）
- [ ] `/cli` での GraphQL ポリシー評価（evaluate_policy）
- [x] fgh のカスタムコマンド対応（プロキシ対象外の場合：gh 直接実行）
- [x] fgh のカスタムコマンド対応（プロキシ対象の場合：fgp `/cli`）
