# GitHub Proxy 設計ドキュメント

## 1. 北極星

GitHub 公式が finer-grained PAT を出すまでの「足し」として、AI を従えた人間に使ってもらう。

**ターゲット**:
- Classic PAT は広すぎて AI に渡すのが怖い人
- Fine-grained PAT では collaborator リポジトリにアクセスできなくて困ってる人
- Fine-grained PAT の permission 粒度では足りない人（後述）

**ゴール**:
- GitHub が「あ、こういう権限分離が必要なんだ」と気づくリファレンス実装になる
- 最終的に公式機能として取り込まれたら、このプロキシは役目を終える

---

## 2. 召し抱えられ戦略

OSS 覇権ではなく「公式に召し抱えられる」エグジットを狙う。

```
[自分で使う] ← 今ここ
    ↓
[OSS 公開: PR スコープで最小価値]
    ↓
[ユーザーの声で拡張: Issues, Projects, Actions, ...]
    ↓
[GitHub 公式が finer-grained PAT を実装]
    ↓
[役目を終える]
```

### 公式に取り込まれやすい設計

- **GitHub の既存概念と整合** — scope, permission の命名と矛盾しない
- **束ね方が直感的** — 「これが欲しかった」と思える
- **束ね方が最小驚き** — 「え、これも含まれてたの？」がない
- **最小粒度を公開仕様として維持** — ユーザーが細かく制御できる

---

## 3. 設計思想

### 3.1 GitHub PAT の問題

| 軸 | 問題 |
|----|------|
| **束ねる粒度** | Fine-grained PAT でもまだ荒い（下記参照） |
| **束 × リポジトリの直積** | permission A を repo-a に、permission B を repo-b に、ができない |
| **リポジトリタイプ** | Fine-grained PAT は collaborator リポジトリにアクセスできない |

**束ねる粒度の具体例**:

| 公式の permission | 一緒くたになってるもの | 分離したいユースケース |
|------------------|---------------------|---------------------|
| `contents:write` | push + merge | AI に push させたいが merge は人間がやりたい |
| `pull-requests:write` | PR 作成 + review 投稿 | PR 作成だけ許可、review は禁止したい |
| `pull-requests:write` | approve + request_changes | approve は禁止、comment だけ許可したい |

**裏取り**: merge が `contents:write` に含まれ `pull-requests:write` には含まれないことは [REST API endpoints for pull requests](https://docs.github.com/en/rest/pulls/pulls)（`PUT /pulls/{n}/merge` の Required permissions）および [Permissions required for fine-grained personal access tokens](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens) で確認。

GitHub Community でも同様の要望がある:
- [#69459](https://github.com/orgs/community/discussions/69459): approve と merge を分離したい
- [#182732](https://github.com/orgs/community/discussions/182732): pulls:write を contribute と merge に分離してほしい（osabe が投稿）

### 3.2 github-proxy の解決策

| 問題 | 解決 | 状態 |
|------|------|------|
| 束 × リポジトリの直積 | AWS IAM 式ポリシー評価（action × repo） | Done (#001) |
| リポジトリタイプ | Classic PAT 経由でプロキシ | Done |
| 束ねる粒度 | 層1/層2 の分離 | Open (#003) |

### 3.3 Action の2層設計

AWS IAM のモデルに倣う:

```
層1: Primitive Action（最小粒度）
  - REST API endpoint × HTTP method の粒度
  - GraphQL mutation の粒度
  - 例: pr:create, pr:comment, pr:approve, pr:merge

層2: Bundle（便利セット）
  - 層1 を束ねたもの
  - 例: pulls:contribute = pr:create + pr:comment + pr:review
```

**設計原則**:
- 層1と層2は独立して設計できる
- 層2は層1の上に構築される
- ユーザーはどちらの粒度でも設定ファイルに書ける
- 層1が公開仕様として維持される（AWS の s3:GetObject のように）

### 3.4 スコープの広げ方

最初は PR に限定し、ユーザーの声で広げる:

```
[PR] ← 最初
  ↓ Issue 対応の要望
[PR + Issues]
  ↓ Projects 対応の要望
[PR + Issues + Projects]
  ↓ ...
```

自由研究化を防ぐ。ユーザーの声が羅針盘。

---

## 4. 現状のアーキテクチャ

```
DevContainer (Claude Code)
    ↓ HTTP
ホスト側プロキシ (github-proxy)
    ↓ ポリシー評価 → Classic PAT 付与
GitHub API / github.com (git)
```

### 4.1 ポリシー評価（AWS IAM 式）

1. デフォルト: 暗黙の Deny
2. 一つでも Deny にマッチ → 即拒否（**Deny always wins**）
3. 一つでも Allow にマッチ → 許可
4. 何もマッチしない → 拒否

### 4.2 設定ファイル形式

```json
{
  "classic_pat": "ghp_xxx",
  "rules": [
    { "effect": "allow", "actions": ["pulls:contribute"], "repos": ["owner/repo"] },
    { "effect": "deny", "actions": ["pulls:merge"], "repos": ["*"] }
  ]
}
```
