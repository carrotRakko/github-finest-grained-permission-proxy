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
ユーザー(AI) ---> fgh ---> fgp ---> GitHub API
                            |
                            +---> gh (subprocess) ---> GitHub API
```

| コンポーネント | どこで動く | 役割 |
|---------------|-----------|------|
| **fgh** | devcontainer | CLI。薄いクライアント。全リクエストを fgp に転送する |
| **fgp** | ホスト | HTTP サーバー。PAT 管理、ポリシー評価、GitHub API 実行 |
| **gh** | ホスト | GitHub 公式 CLI。fgp から subprocess で呼ばれる |

---

## fgh の責任

**薄いクライアントに徹する**

- 全てのコマンドを fgp の `/cli` エンドポイントに転送
- ルーティング判断をしない（fgp に委ねる）
- PAT を持たない

```bash
# fgh が受けたコマンド
fgh issue list -R owner/repo
fgh sub-issue list 123
fgh api /repos/owner/repo/issues

# 全て fgp の /cli に転送
POST /cli
{
  "args": ["issue", "list"],
  "repo": "owner/repo"
}
```

---

## fgp の責任

1. **PAT 管理** - classic PAT × 1 + fine-grained PAT × n を保持
2. **PAT 選択** - repo に基づいて適切な PAT を選択
3. **ポリシー評価** - action × repo でアクセス制御
4. **コマンド実行** - gh subprocess または直接 GraphQL 実行

### PAT 選択ロジック

```
1. repo にマッチする fine-grained PAT を探す
2. マッチしたらそれを使う
3. どれにもマッチしなければ classic PAT（fallback）
```

### 設定ファイル形式

```json
{
  "classic_pat": "ghp_xxx",
  "fine_grained_pats": [
    {
      "pat": "github_pat_delight_xxx",
      "repos": ["delight-co/*"]
    },
    {
      "pat": "github_pat_carrotRakko_xxx",
      "repos": ["carrotRakko/*"]
    }
  ],
  "rules": [
    { "effect": "allow", "actions": ["*"], "repos": ["delight-co/*"] },
    { "effect": "allow", "actions": ["subissues:*", "issues:*"], "repos": ["anthropic/claude-code"] },
    { "effect": "deny", "actions": ["pr:merge_*"], "repos": ["*"] }
  ]
}
```

---

## エンドポイント

| エンドポイント | 用途 | クライアント |
|---------------|------|-------------|
| `/cli` | CLI コマンド実行 | fgh |
| `/git/{owner}/{repo}.git/...` | git smart HTTP | git (clone/push) |

`/cli` に一本化。fgh は `/cli` のみを叩く。

---

## コマンド実行フロー

### 標準 gh コマンド

```
fgh issue list -R delight-co/repo
  ↓
fgp /cli: ["issue", "list"]
  ↓
PAT 選択: delight-co/* → fine-grained PAT
  ↓
ポリシー評価: issues:read × delight-co/repo → Allow
  ↓
gh issue list -R delight-co/repo (subprocess, 選択した PAT で)
  ↓
結果を fgh に返す
```

### カスタムコマンド (sub-issue 等)

```
fgh sub-issue list 123 -R carrotRakko/terachess
  ↓
fgp /cli: ["sub-issue", "list", "123"]
  ↓
PAT 選択: carrotRakko/* → fine-grained PAT (or classic if not found)
  ↓
ポリシー評価: subissues:list × carrotRakko/terachess → Allow
  ↓
GraphQL 実行 (選択した PAT で)
  ↓
結果を fgh に返す
```

---

## 進化の計画

### Phase 1: GraphQL 直実装（現在）

カスタムコマンド（sub-issue, discussions 等）は fgp 内で GraphQL を直接実行。

```
fgp
  └── execute_sub_issue_cli()  # GraphQL 直叩き
  └── execute_discussions_cli()  # GraphQL 直叩き
```

### Phase 2: gh extension 化（将来）

カスタムコマンドを gh extension として切り出し、fgp は subprocess で呼ぶ。

```
fgp
  └── gh sub-issue (extension)
  └── gh discussions (extension)
```

**メリット**:
- gh extension として個別に「召し抱えられ」を狙える
- fgp はポリシー評価に専念

---

## 召し抱えられ戦略との関係

2層の召し抱えられポイント:

1. **fgp のポリシー設計** - action × repo、層1/層2 の粒度設計
   - GitHub が「こういう権限分離が必要」と気づくリファレンス

2. **gh extension** - sub-issue, discussions, project-v2 等
   - gh 公式コマンドとして取り込まれる可能性

---

## 実装状況

- [x] `/cli` エンドポイント（fgp）
- [ ] fgh を薄いクライアント化（全コマンドを /cli に転送）
- [ ] PAT 選択ロジック（fine-grained × n + classic fallback）
- [ ] 旧エンドポイント削除（/proxy-repos, /graphql-ops/sub-issues/*）
- [ ] fgh から sub-issue 実装を削除（fgp に一元化）
