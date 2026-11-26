# glance 技術構成

作成日: 2026-11-26
状態: 初版（実装前）。1番目の段階（リアルタイム画面）で作る分を詳しく書く。2番目以降の分（日次バッチ、チャットなど）は、その段階の前に足す。

画面の設計は [screen_design.md](screen_design.md)、サーバーの置き方は [infrastructure_design.md](infrastructure_design.md)、リアルタイムのデータの取り方は [data_sources.md](data_sources.md) §5。

---

## 1. 構成の方針

**画面は Next.js の静的書き出し（`output: 'export'`）にし、VPS では FastAPI が API と画面の静的ファイルの両方を出す。常駐するのは FastAPI だけ。**

```
ブラウザ ──→ Cloudflare ──→ Tunnel ──→ FastAPI（127.0.0.1:8101）
                                         ├─ /api/*  … API（ログイン・サイト設定・リアルタイム）
                                         └─ /*      … 画面（Next.js で書き出した HTML・JS）
```

理由:

- 管理画面で、検索エンジンに見せるページがない。サーバーでの描画（SSR・ISR）は要らない。
- 画面と API が同じオリジンになる。ログインのクッキーをそのまま使え、画面と API の間の中継や共有シークレットが要らない。
- VPS に Node.js を常駐させずに済み、メモリが減る。画面のビルドは手元で行うので、VPS でのビルドの負荷もない。

静的書き出しの制約:

- Next.js のサーバーの機能（ミドルウェア、Route Handlers、サーバーでの描画、画像の最適化）は使わない。
- URL に ID を含む画面は、パスではなくクエリ文字列にする（例: `/conversations?id=12`）。書き出しの時点で ID がわからないため。

## 2. 言語・ライブラリ

| 区分 | 選定 |
|---|---|
| Python | 3.14、uv |
| API | FastAPI、uvicorn |
| DB | PostgreSQL 16、SQLAlchemy 2（非同期）、psycopg 3、Alembic |
| Google の API | `google-analytics-data`（Data API。リアルタイムも）、`google-analytics-admin`（プロパティの一覧・情報） |
| Google ログイン | `google-auth`・`google-auth-oauthlib`（Web サーバーの手順、ID トークンの検証） |
| 暗号化 | `cryptography` の Fernet |
| 画面 | Next.js（静的書き出し）、React、TypeScript、Tailwind CSS、shadcn/ui、Recharts（shadcn/ui の Chart） |
| 画面のパッケージ管理 | npm |

各ライブラリの版は、実装の最初にその時点の安定版で固める。

## 3. リポジトリの構成

```
glance/
├── src/glance/
│   ├── main.py         # FastAPI の起動。/api と画面の静的ファイルをまとめる
│   ├── config.py       # 環境変数の読み込み（§9）
│   ├── auth/           # Google ログイン、セッション、トークンの暗号化
│   ├── google/         # GA4 Data API・Admin API の呼び出し
│   ├── realtime/       # リアルタイムの取得とサイト横断のまとめ
│   ├── sites/          # サイト設定
│   ├── db/             # テーブルの定義、接続
│   └── batch/          # 日次バッチ（2番目の段階から）
├── migrations/         # Alembic
├── web/                # Next.js（静的書き出し）
├── deploy/             # VPS で使うもの（systemd のユニット、リリースの流れ）
├── scripts/            # 手元で人が実行するもの（反映など）
├── tests/
└── docs/
```

## 4. ログイン（Google）

方針は [infrastructure_design.md](infrastructure_design.md) §5。ここでは手順を書く。**OAuth は FastAPI で受ける。** 更新トークンを使うのは API なので、トークンが画面側のコードに出ないようにする。

**流れ**

1. 画面の「Google でログイン」→ `GET /api/auth/login`。
2. サーバーが `state` と PKCE の `code_verifier` を作り、期限10分のクッキー（`HttpOnly`・`Secure`）に入れて、Google の同意画面へ送る。
   - 許可の範囲: `openid`・`email`・`profile`・`analytics.readonly`・`webmasters.readonly`
   - `access_type=offline`（更新トークンをもらう）
3. Google から `GET /api/auth/callback` に戻る。`state` を照合し、認可コードをトークンに替える。
4. ID トークンを検証する（発行元、宛先、メールアドレスが確認済みか）。
5. メールアドレスが許可リスト（`GLANCE_ALLOWED_EMAILS`）になければ、ログイン画面に戻して「このアカウントは使えません」と出す。トークンは保存しない。
6. 利用者（`users`）を作るか更新し、更新トークンを暗号化して入れる。
7. セッションを作り、`/` へ戻す。

**更新トークンがもらえないとき**: Google は、2回目以降の同意では更新トークンを返さない。戻ってきたときに更新トークンがなく、保存済みのものもない（または失効している）ときは、`prompt=consent` を付けてもう一度同意画面へ送る。

**セッション**

- ランダムな ID をクッキー（`HttpOnly`・`Secure`・`SameSite=Lax`）に入れる。DB（`sessions`）には ID のハッシュだけを入れる。
- 期限は30日。ログアウトで消す。
- 書き込みの要求（POST・PATCH・DELETE）は JSON だけを受ける。`SameSite=Lax` と合わせて、別のサイトからの書き込み（CSRF）を防ぐ。

**Google の API を呼ぶとき**

- 利用者ごとに、更新トークンから作った認証情報（`google.oauth2.credentials.Credentials`）をメモリに持つ。アクセストークン（約1時間）が切れたら、ライブラリが自動で取り直す。
- 更新トークンが失効していたら（`invalid_grant`）、API は 401 と `{"code": "reauth_required"}` を返す。画面は「ログインし直してください」と出す。

## 5. トークンの暗号化

- Fernet（`cryptography`）で暗号化して DB に入れる。鍵は `/etc/glance/glance.env` の `GLANCE_TOKEN_KEY`。
- 鍵を入れ替えるときは、新しい鍵と古い鍵を並べて読み（`MultiFernet`）、保存し直すときに新しい鍵で暗号化する。

## 6. API（1番目の段階の分）

`/api/auth/login`・`/api/auth/callback` 以外は、ログインが要る。サイトは、ログイン中の利用者の顧客（`tenant_id`）のものだけを扱う。

| メソッド・パス | 内容 |
|---|---|
| `GET /api/auth/login` | Google の同意画面へ送る（§4） |
| `GET /api/auth/callback` | Google から戻る。ログインを済ませて `/` へ |
| `POST /api/auth/logout` | セッションを消す |
| `GET /api/me` | ログイン中の利用者（メールアドレス）。未ログインなら 401 |
| `GET /api/ga4/properties` | ログインしたアカウントが見られる GA4 のプロパティの一覧（Admin API の `accountSummaries.list`）。アカウントごとにまとめ、追加済みかどうかも付ける |
| `GET /api/sites` | サイトの一覧（並び順） |
| `POST /api/sites` | サイトを追加する。GA4 のプロパティ ID を受け取り、名前とタイムゾーンを Admin API の `properties.get` から取って入れる。GA4 の接続設定（`connections`）も作る |
| `PATCH /api/sites/{id}` | 名前・並び順を変える |
| `DELETE /api/sites/{id}` | サイトを消す（接続設定も消す） |
| `GET /api/realtime` | 全サイトのリアルタイムを取る（下記） |

### 6.1 `GET /api/realtime`

- サイトごとに、[data_sources.md](data_sources.md) §5 の3回の呼び出しを行う。全サイト・全呼び出しを並行して行う（非同期のクライアント）。
- 1サイトの待ち時間の上限は10秒。超えたサイト、失敗したサイトは `status: "error"` にし、ほかのサイトの結果は返す。
- `minutesAgo` は値のない分を 0 で埋め、30分前から今までの30個にそろえる。
- 直近5分の値は、1回目の呼び出しの2つめの期間から取る（分ごとの値は足さない。[data_sources.md](data_sources.md) §5）。
- 全サイトの合計は、サーバーで出す。
- 上位の記事は、サイトごとの上位20件だけを返す。全サイトをまとめた上位20件は、画面で選んだサイトに合わせて画面が並べ直す（[screen_design.md](screen_design.md) §3）。
- 結果は DB に入れない。キャッシュもしない（押すたびに取る）。

応答の形（数字は例）:

```json
{
  "fetched_at": "2026-11-26T14:32:05+09:00",
  "sites": [
    {
      "site_id": 1,
      "name": "LogiShift",
      "status": "ok",
      "last_30_min": {"page_views": 120, "active_users": 45, "key_events": 2},
      "last_5_min": {"page_views": 18, "active_users": 9, "key_events": 0},
      "per_minute": [
        {"minutes_ago": 29, "page_views": 3, "active_users": 2},
        {"minutes_ago": 28, "page_views": 5, "active_users": 4}
      ],
      "top_pages": [{"title": "記事のタイトル", "page_views": 12, "active_users": 8}]
    },
    {"site_id": 2, "name": "TechShift", "status": "error", "error": "timeout"}
  ],
  "total": {
    "last_30_min": {"page_views": 300, "active_users": 110, "key_events": 3},
    "last_5_min": {"page_views": 40, "active_users": 21, "key_events": 0}
  }
}
```

- `per_minute` は30個（例では途中を省いた）。
- `error` の種類: `timeout`（時間切れ）、`permission_denied`（プロパティを見る権限がない）、`quota`（上限に当たった）、`error`（その他）。
- `total` は、`status: "ok"` のサイトだけで出す。

## 7. 画面（Next.js）

- 静的書き出しで、ページは `/login`・`/`（リアルタイム）・`/settings/sites` の3つ。中身は [screen_design.md](screen_design.md)。
- データは、画面から `/api` を呼んで取る（ブラウザ側）。401 が返ったら `/login` へ移す（`reauth_required` のときは、理由を出してから移す）。
- 画面に出す文字は、すべて React が描く（エスケープされる）。`dangerouslySetInnerHTML` は使わない（[overview.md](overview.md) §5）。

## 8. VPS での動かし方

| 項目 | 内容 |
|---|---|
| Linux ユーザー | `glance`（ログインできないシステムユーザー）。置き場所は `/srv/glance`（750） |
| リリース | `/srv/glance/releases/<日時>-<コミット>/`。動いているリリースは `/srv/glance/current`（リンク） |
| サービス | systemd で `glance-api`（uvicorn。127.0.0.1:8101）と `glance-cloudflared`（Glance 用の Tunnel） |
| 環境変数 | `/etc/glance/glance.env`（root・600）。systemd が読んで渡す |
| DB | LeadHub の PostgreSQL のコンテナに、データベース `glance` と DB ユーザー `glance` を作る（コンテナの管理ユーザーで1回だけ）。`glance` は自分のデータベースにだけ入れる |

## 9. 環境変数

値は git に書かない。`/etc/glance/glance.env`（本番）と手元の `.env` にだけ置く。

| 名前 | 中身 |
|---|---|
| `GLANCE_DATABASE_URL` | DB の接続 URI |
| `GLANCE_TOKEN_KEY` | 更新トークンを暗号化する鍵（Fernet） |
| `GLANCE_GOOGLE_CLIENT_ID` | OAuth クライアントの ID |
| `GLANCE_GOOGLE_CLIENT_SECRET` | OAuth クライアントの秘密 |
| `GLANCE_ALLOWED_EMAILS` | ログインを許すメールアドレス（カンマ区切り） |
| `GLANCE_PUBLIC_URL` | 画面の URL。Google から戻る先（`/api/auth/callback`）を組み立てるのに使う |

Cloudflare Tunnel の認証情報は、cloudflared の設定ファイルとして別に置く（[infrastructure_design.md](infrastructure_design.md) §4）。

## 10. 反映の手順

LeadHub と同じく、**手元で人がスクリプト（`scripts/deploy_prod.sh`）を実行する。** GitHub の main にあるコミットだけを出す。

1. **手元**: 出すコミットを一時ディレクトリに書き出し、そこで画面をビルドする（`npm ci`・`npm run build`）。コミットしていない変更が混ざらないようにするため。
2. **手元**: コードと書き出した画面を1つのアーカイブにして VPS へ送る。
3. **VPS**: リリースのディレクトリに展開する。uv で Python の環境を作り、`alembic upgrade head` を当てる。`current` を付け替えて `glance-api` を再起動する。
4. **戻し方**: `current` を前のリリースに付け替えて、再起動する。マイグレーションは自動では戻さない。

HTML は Cloudflare の既定ではキャッシュされず、JS・CSS はファイル名に中身のハッシュが入る。そのため、反映の後に Cloudflare のキャッシュを消す手順は要らない。

## 11. 手元での開発

- **DB**: Glance 用の PostgreSQL 16 を Docker で立てる。LeadHub の手元の DB とは別にする。
- **Google ログイン**: OAuth クライアントの戻り先に、手元の URL（`http://localhost:<ポート>/api/auth/callback`）も登録する。
- **画面**: `next dev` で動かし、`/api` への要求を手元の FastAPI に中継する（開発のときだけの設定）。
- **テスト**: API は pytest。Google の API の呼び出しは、記録した応答に差し替えて試す。
