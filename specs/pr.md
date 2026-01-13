# PR 層1仕様

PR（Pull Request）関連の Primitive Action 定義。

REST API と GraphQL API を調査し、細かい方を採用して action を定義した。

**GraphQL に関する注意**: 本仕様の GraphQL 列は、その query/mutation を**純粋に単独で**使う場合を想定している。GraphQL は 1 リクエストで複数リソースを横断取得できるため、複雑な query を許可すると意図しないデータへのアクセス（抜け穴）が発生しうる。Proxy 実装時は query 全体の解析が必要になる可能性がある。

---

## 層1: Primitive Action

### PR 基本操作

| Action | REST Endpoint | Method | REST Params | GraphQL | GQL Params | 説明 |
|--------|---------------|--------|-------------|---------|------------|------|
| `pr:list` | `/repos/{o}/{r}/pulls` | GET | - | (query) | - | PR 一覧取得 |
| `pr:get` | `/repos/{o}/{r}/pulls/{n}` | GET | - | (query) | - | PR 詳細取得 |
| `pr:create` | `/repos/{o}/{r}/pulls` | POST | - | `createPullRequest` | - | PR 作成 |
| `pr:create_draft` | `/repos/{o}/{r}/pulls` | POST | draft=true | `createPullRequest` | draft=true | ドラフト PR 作成 |
| `pr:update` | `/repos/{o}/{r}/pulls/{n}` | PATCH | title, body, base | `updatePullRequest` | title, body, baseRefName | PR 更新（タイトル、本文、ベース） |
| `pr:close` | `/repos/{o}/{r}/pulls/{n}` | PATCH | state=closed | `closePullRequest` | - | PR クローズ |
| `pr:reopen` | `/repos/{o}/{r}/pulls/{n}` | PATCH | state=open | `reopenPullRequest` | - | PR 再オープン |
| `pr:convert_to_draft` | `/repos/{o}/{r}/pulls/{n}` | PATCH | draft=true | `convertPullRequestToDraft` | - | ドラフトに変換 |
| `pr:mark_ready` | `/repos/{o}/{r}/pulls/{n}` | PATCH | draft=false | `markPullRequestReadyForReview` | - | Ready for review に変換 |
| `pr:commits` | `/repos/{o}/{r}/pulls/{n}/commits` | GET | - | (query) | - | PR のコミット一覧 |
| `pr:files` | `/repos/{o}/{r}/pulls/{n}/files` | GET | - | (query) | - | PR のファイル一覧 |
| `pr:merge_status` | `/repos/{o}/{r}/pulls/{n}/merge` | GET | - | (query) | - | マージ状態確認 |
| `pr:merge_commit` | `/repos/{o}/{r}/pulls/{n}/merge` | PUT | merge_method=merge | `mergePullRequest` | mergeMethod=MERGE | マージコミットでマージ |
| `pr:merge_squash` | `/repos/{o}/{r}/pulls/{n}/merge` | PUT | merge_method=squash | `mergePullRequest` | mergeMethod=SQUASH | スカッシュマージ |
| `pr:merge_rebase` | `/repos/{o}/{r}/pulls/{n}/merge` | PUT | merge_method=rebase | `mergePullRequest` | mergeMethod=REBASE | リベースマージ |
| `pr:update_branch` | `/repos/{o}/{r}/pulls/{n}/update-branch` | PUT | - | `updatePullRequestBranch` | - | ブランチ更新（upstream から） |
| `pr:revert` | - | - | - | `revertPullRequest` | - | マージ済み PR を revert する PR 作成 |

### Auto Merge / Merge Queue（GraphQL のみ）

| Action | REST Endpoint | Method | REST Params | GraphQL | GQL Params | 説明 |
|--------|---------------|--------|-------------|---------|------------|------|
| `pr:auto_merge_enable` | - | - | - | `enablePullRequestAutoMerge` | mergeMethod | 自動マージ有効化 |
| `pr:auto_merge_disable` | - | - | - | `disablePullRequestAutoMerge` | - | 自動マージ無効化 |
| `pr:queue_add` | - | - | - | `enqueuePullRequest` | - | マージキューに追加 |
| `pr:queue_remove` | - | - | - | `dequeuePullRequest` | - | マージキューから削除 |

### File Viewed（GraphQL のみ）

| Action | REST Endpoint | Method | REST Params | GraphQL | GQL Params | 説明 |
|--------|---------------|--------|-------------|---------|------------|------|
| `pr:file_mark_viewed` | - | - | - | `markFileAsViewed` | - | ファイルを閲覧済みにマーク |
| `pr:file_unmark_viewed` | - | - | - | `unmarkFileAsViewed` | - | 閲覧済みマークを解除 |

### General Comments（Issues API 経由）

PR の general comment は Issues API を使用。「PR は Issue でもある」ため。

| Action | REST Endpoint | Method | REST Params | GraphQL | GQL Params | 説明 |
|--------|---------------|--------|-------------|---------|------------|------|
| `pr:comment_list_all` | `/repos/{o}/{r}/issues/comments` | GET | - | (query) | - | 全コメント一覧 |
| `pr:comment_list` | `/repos/{o}/{r}/issues/{n}/comments` | GET | - | (query) | - | PR のコメント一覧 |
| `pr:comment_get` | `/repos/{o}/{r}/issues/comments/{id}` | GET | - | (query) | - | コメント取得 |
| `pr:comment_create` | `/repos/{o}/{r}/issues/{n}/comments` | POST | - | `addComment` | - | コメント作成 |
| `pr:comment_update` | `/repos/{o}/{r}/issues/comments/{id}` | PATCH | - | `updateIssueComment` | - | コメント更新 |
| `pr:comment_delete` | `/repos/{o}/{r}/issues/comments/{id}` | DELETE | - | `deleteIssueComment` | - | コメント削除 |

### Review Comments（Inline / Diff へのコメント）

| Action | REST Endpoint | Method | REST Params | GraphQL | GQL Params | 説明 |
|--------|---------------|--------|-------------|---------|------------|------|
| `pr:review_comment_list_all` | `/repos/{o}/{r}/pulls/comments` | GET | - | (query) | - | 全レビューコメント一覧 |
| `pr:review_comment_list` | `/repos/{o}/{r}/pulls/{n}/comments` | GET | - | (query) | - | PR のレビューコメント一覧 |
| `pr:review_comment_get` | `/repos/{o}/{r}/pulls/comments/{id}` | GET | - | (query) | - | レビューコメント取得 |
| `pr:review_comment_create` | `/repos/{o}/{r}/pulls/{n}/comments` | POST | - | `addPullRequestReviewComment` | - | レビューコメント作成 |
| `pr:review_comment_update` | `/repos/{o}/{r}/pulls/comments/{id}` | PATCH | - | `updatePullRequestReviewComment` | - | レビューコメント更新 |
| `pr:review_comment_delete` | `/repos/{o}/{r}/pulls/comments/{id}` | DELETE | - | `deletePullRequestReviewComment` | - | レビューコメント削除 |
| `pr:review_comment_reply` | `/repos/{o}/{r}/pulls/{n}/comments/{id}/replies` | POST | - | `addPullRequestReviewThreadReply` | - | レビューコメント返信 |

### Review Threads（GraphQL のみ）

| Action | REST Endpoint | Method | REST Params | GraphQL | GQL Params | 説明 |
|--------|---------------|--------|-------------|---------|------------|------|
| `pr:thread_create` | - | - | - | `addPullRequestReviewThread` | - | 新しいスレッド追加 |
| `pr:thread_resolve` | - | - | - | `resolveReviewThread` | - | スレッドを解決済みにマーク |
| `pr:thread_unresolve` | - | - | - | `unresolveReviewThread` | - | 解決済みを解除 |

### Reviews（Approve / Request Changes / Comment）

| Action | REST Endpoint | Method | REST Params | GraphQL | GQL Params | 説明 |
|--------|---------------|--------|-------------|---------|------------|------|
| `pr:review_list` | `/repos/{o}/{r}/pulls/{n}/reviews` | GET | - | (query) | - | レビュー一覧 |
| `pr:review_get` | `/repos/{o}/{r}/pulls/{n}/reviews/{id}` | GET | - | (query) | - | レビュー取得 |
| `pr:review_pending` | `/repos/{o}/{r}/pulls/{n}/reviews` | POST | event=(省略) | `addPullRequestReview` | - | 保留レビュー作成 |
| `pr:approve` | `/repos/{o}/{r}/pulls/{n}/reviews` | POST | event=APPROVE | `addPullRequestReview` | event=APPROVE | Approve |
| `pr:request_changes` | `/repos/{o}/{r}/pulls/{n}/reviews` | POST | event=REQUEST_CHANGES | `addPullRequestReview` | event=REQUEST_CHANGES | Request Changes |
| `pr:review_comment_only` | `/repos/{o}/{r}/pulls/{n}/reviews` | POST | event=COMMENT | `addPullRequestReview` | event=COMMENT | Comment（approve/request_changes なし） |
| `pr:review_update` | `/repos/{o}/{r}/pulls/{n}/reviews/{id}` | PUT | - | `updatePullRequestReview` | - | レビューサマリー更新 |
| `pr:review_delete` | `/repos/{o}/{r}/pulls/{n}/reviews/{id}` | DELETE | - | `deletePullRequestReview` | - | 未送信レビュー削除 |
| `pr:review_comments` | `/repos/{o}/{r}/pulls/{n}/reviews/{id}/comments` | GET | - | (query) | - | レビューのコメント一覧 |
| `pr:review_dismiss` | `/repos/{o}/{r}/pulls/{n}/reviews/{id}/dismissals` | PUT | - | `dismissPullRequestReview` | - | レビュー却下 |
| `pr:review_submit_approve` | `/repos/{o}/{r}/pulls/{n}/reviews/{id}/events` | POST | event=APPROVE | `submitPullRequestReview` | event=APPROVE | 保留→Approve 送信 |
| `pr:review_submit_request_changes` | `/repos/{o}/{r}/pulls/{n}/reviews/{id}/events` | POST | event=REQUEST_CHANGES | `submitPullRequestReview` | event=REQUEST_CHANGES | 保留→Request Changes 送信 |
| `pr:review_submit_comment` | `/repos/{o}/{r}/pulls/{n}/reviews/{id}/events` | POST | event=COMMENT | `submitPullRequestReview` | event=COMMENT | 保留→Comment 送信 |

### Review Requests（レビュー依頼）

| Action | REST Endpoint | Method | REST Params | GraphQL | GQL Params | 説明 |
|--------|---------------|--------|-------------|---------|------------|------|
| `pr:reviewer_list` | `/repos/{o}/{r}/pulls/{n}/requested_reviewers` | GET | - | (query) | - | レビュー依頼者一覧 |
| `pr:reviewer_request` | `/repos/{o}/{r}/pulls/{n}/requested_reviewers` | POST | - | `requestReviews` | - | レビュー依頼 |
| `pr:reviewer_remove` | `/repos/{o}/{r}/pulls/{n}/requested_reviewers` | DELETE | - | `requestReviews` | - | レビュー依頼削除 |

---

## 層1 Action 数

| カテゴリ | 数 |
|----------|-----|
| PR 基本操作 | 17 |
| Auto Merge / Merge Queue | 4 |
| File Viewed | 2 |
| General Comments | 6 |
| Review Comments | 7 |
| Review Threads | 3 |
| Reviews | 13 |
| Review Requests | 3 |
| **合計** | **55** |

---

## 層2: Bundle

層1 を束ねた便利セット。

### 公式互換 Bundle

Fine-grained PAT の `pull-requests` permission と同じ範囲。公式が finer-grained になったときの移行パスを確保。

| Bundle | 展開される層1 Actions |
|--------|----------------------|
| `pull-requests:read` | `pr:list`, `pr:get`, `pr:commits`, `pr:files`, `pr:merge_status`, `pr:reviewer_list`, `pr:review_list`, `pr:review_get`, `pr:review_comments`, `pr:review_comment_list_all`, `pr:review_comment_list`, `pr:review_comment_get`, `pr:comment_list_all`, `pr:comment_list`, `pr:comment_get` |
| `pull-requests:write` | `pull-requests:read` + `pr:create`, `pr:create_draft`, `pr:update`, `pr:close`, `pr:reopen`, `pr:convert_to_draft`, `pr:mark_ready`, `pr:update_branch`, `pr:reviewer_request`, `pr:reviewer_remove`, `pr:review_pending`, `pr:approve`, `pr:request_changes`, `pr:review_comment_only`, `pr:review_update`, `pr:review_delete`, `pr:review_dismiss`, `pr:review_submit_approve`, `pr:review_submit_request_changes`, `pr:review_submit_comment`, `pr:review_comment_create`, `pr:review_comment_update`, `pr:review_comment_delete`, `pr:review_comment_reply`, `pr:comment_create`, `pr:comment_update`, `pr:comment_delete` |

**調査元**: [Permissions required for fine-grained personal access tokens](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens)（REST API ベース。GraphQL の注意は冒頭参照）

### 公式 permission に含まれない操作

| 操作 | 必要な permission | 備考 |
|------|------------------|------|
| `pr:merge_*` | `contents:write` | REST/GraphQL 共通 |
| `pr:auto_merge_*` | `contents:write` + `pull-requests:write` | GraphQL のみ |
| `pr:queue_*` | 未確定 | GraphQL のみ、ドキュメント不十分 |
| `pr:file_*_viewed` | 未確定 | GraphQL のみ、ドキュメント不十分 |
| `pr:thread_*` | 未確定 | GraphQL のみ、ドキュメント不十分 |
| `pr:revert` | 未確定 | GraphQL のみ、ドキュメント不十分 |

### github-proxy 独自 Bundle

公式より細かい粒度で制御したい場合の便利セット。

| Bundle | 展開される層1 Actions | ユースケース |
|--------|----------------------|-------------|
| `pulls:contribute` | `pull-requests:read` + `pr:create`, `pr:create_draft`, `pr:update`, `pr:convert_to_draft`, `pr:mark_ready`, `pr:comment_create`, `pr:comment_update`, `pr:review_comment_create`, `pr:review_comment_update`, `pr:review_comment_reply`, `pr:review_pending`, `pr:approve`, `pr:request_changes`, `pr:review_comment_only`, `pr:review_update`, `pr:review_submit_approve`, `pr:review_submit_request_changes`, `pr:review_submit_comment`, `pr:reviewer_request` | AI に PR 作成・レビューを許可、close/delete/merge は禁止 |

**包含関係**:
```
pull-requests:read ⊂ pulls:contribute ⊂ pull-requests:write
```

---

## 設計判断メモ

### REST と GraphQL の突き合わせ

両方を調査し、細かい方を採用した。

| 操作 | REST | GraphQL | 採用した粒度 |
|------|------|---------|-------------|
| draft PR 作成 | パラメータ分岐 | パラメータ分岐 | 分ける（`pr:create` / `pr:create_draft`） |
| draft 変換 | パラメータ分岐 | 独立 mutation | 分ける（`pr:convert_to_draft`） |
| ready 変換 | パラメータ分岐 | 独立 mutation | 分ける（`pr:mark_ready`） |
| close/reopen | パラメータ分岐 | 独立 mutation | 分ける（`pr:close` / `pr:reopen`） |
| merge method | パラメータ分岐 | パラメータ分岐 | 分ける（`pr:merge_commit` / `pr:merge_squash` / `pr:merge_rebase`） |
| review event | パラメータ分岐 | パラメータ分岐 | 分ける（`pr:approve` / `pr:request_changes` / `pr:review_comment_only`） |

### 分岐パラメータの判断基準

- **傾向**: boolean または enum 型のパラメータは分岐候補
- **ユースケース**: 「Aは許可、Bは禁止」が想定できるか
- **定義としては未確定**: 経験を積みながらパターンを確定していく

### GraphQL のみの機能

以下は REST API では提供されていない:

- Auto Merge（enablePullRequestAutoMerge / disablePullRequestAutoMerge）
- Merge Queue（enqueuePullRequest / dequeuePullRequest）
- File Viewed（markFileAsViewed / unmarkFileAsViewed）
- Review Threads（addPullRequestReviewThread / resolveReviewThread / unresolveReviewThread）
- Revert PR（revertPullRequest）
