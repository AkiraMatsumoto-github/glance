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
| 画面 | Next.js（静的書き出し）、React、TypeScript、Tailwind CSS、shadcn/ui、Recharts |

グラフは Recharts を直接使う。shadcn/ui の Chart（`chart.tsx`）は、色を CSS として差し込むのに `dangerouslySetInnerHTML` を使うため使わない（§7）。
| 画面のパッケージ管理 | npm |

各ライブラリの版は、実装の最初にその時点の安定版で固める。

## 3. リポジトリの構成

```
glance/
├── src/glance/
│   ├── main.py         # FastAPI の起動。/api と画面の静的ファイルをまとめる
│   ├── config.py       # 環境変数の読み込み（§9）
│   ├── logs.py         # 秘密の値をログに出さない（§9）
│   ├── rekey.py        # 暗号化の鍵を入れ替えた後の暗号化し直し（python -m glance.rekey。§5）
│   ├── auth/           # Google ログイン、セッション、クッキー（cookies.py）、トークンの暗号化
│   ├── google/         # Google（GA4 Data API・Admin API・Search Console API）の呼び出し。client.py が入口、real.py が本物、fake.py がダミー
│   ├── bing/           # Bing Webmaster API の呼び出し（client.py。本物とダミー）と、キーの API（routes.py）
│   ├── realtime/       # リアルタイムの取得とサイト横断のまとめ
│   ├── sites/          # サイト設定（routes.py）、Search Console・Bing の紐づけ（links.py）、Search Console のサイトの選び方（gsc.py）、顧客のサイトの取り出し（common.py）、デモ（demo.py）
│   ├── seo/            # SEO の画面の集計（service.py）、応答の形（schemas.py）、期間（periods.py）、デモ（demo.py）
│   ├── sync/           # 取り込み（python -m glance.sync。全体は runner.py、Search Console は gsc.py、Bing は bing.py、取得ログは common.py。sitemap.py・values.py）
│   └── db/             # テーブルの定義、接続
├── migrations/         # Alembic
├── web/                # Next.js（静的書き出し）。app/（ページ）、components/（部品。realtime・seo・sites と共通の部品）、lib/（API・データの取り方・型・書式・SEO の計算）
├── tests/              # pytest。e2e/ は画面の自動テスト（ブラウザで動かす。GLANCE_E2E=1 のときだけ）
└── docs/
（VPS に出すときに deploy/・scripts/ を足す。§8・§10）
```

## 4. ログイン（Google）

方針は [infrastructure_design.md](infrastructure_design.md) §5。ここでは手順を書く。**OAuth は FastAPI で受ける。** 更新トークンを使うのは API なので、トークンが画面側のコードに出ないようにする。

**流れ**

1. 画面の「Google でログイン」→ `GET /api/auth/login`。
2. サーバーが `state` と PKCE の `code_verifier` を作り、期限10分のクッキー（下の「クッキー」）に入れて、Google の同意画面へ送る。
   - 許可の範囲: `openid`・`email`・`profile`・`analytics.readonly`・`webmasters.readonly`
   - `access_type=offline`（更新トークンをもらう）
3. Google から `GET /api/auth/callback` に戻る。`state` を照合し、認可コードをトークンに替える。
4. ID トークンを検証する（発行元、宛先、期限、メールアドレスが確認済みか）。サーバーと Google の時計のずれは10秒まで認める（既定の0秒だと、手元の時計が1秒遅れているだけで「発行時刻より前」として断られた。2026-11-28）。
5. メールアドレスが許可リスト（`GLANCE_ALLOWED_EMAILS`）になければ、ログイン画面に戻して「このアカウントは使えません」と出す。トークンは保存しない。
6. 利用者（`users`）を作るか更新し、更新トークンを暗号化して入れる。初めての人には、その人だけの顧客（`tenants`）を作る。サイト・連携・Bing のキー・取り込んだ数字は顧客ごとに分かれるので、ほかのアカウントのものは見えない（2026-11-28 利用者の決定）。
7. セッションを作り、`/` へ戻す。

**更新トークンがもらえないとき**: Google は、2回目以降の同意では更新トークンを返さない。戻ってきたときに更新トークンがなく、保存済みのものもないときは、`prompt=consent` を付けてもう一度同意画面へ送る。保存済みの更新トークンが失効したとき（API が `reauth_required` を返したとき）は、ログイン画面のボタンが `prompt=consent` 付きになり、同意画面を出してもらい直す。

**セッション**

- ランダムな ID をクッキーに入れる。DB（`sessions`）には ID のハッシュだけを入れる。
- 期限は30日。ログアウトで消す。
- 書き込みの要求（POST・PATCH・DELETE）は JSON だけを受ける。`SameSite=Lax` と合わせて、別のサイトからの書き込み（CSRF）を防ぐ。

**クッキー**（`glance/auth/cookies.py`。2026-11-28 セキュリティレビューの対応）

- どれも `HttpOnly`・`SameSite=Lax`・`Path=/`。名前は、セッションが `glance_session`、同意画面から戻るまでの照合が `glance_oauth_state`・`glance_oauth_verifier`。
- 本番（`GLANCE_PUBLIC_URL` が https）では `Secure` にし、名前に `__Host-` を付ける（`__Host-glance_session` など）。`__Host-` のクッキーは `Secure`・`Path=/`・Domain なしでしか置けないので、同じ親ドメインのほかのサブドメインから同じ名前のクッキーを差し込まれない（セッションの押しつけ、ログインの state の書き換えを防ぐ）。手元（http://localhost）は `Secure` にできないので付けない。

**応答のヘッダー**: 全部の応答（画面・API）に `X-Frame-Options: DENY`・`Content-Security-Policy: frame-ancestors 'none'`（ほかのサイトのフレームに埋め込ませない）と `X-Content-Type-Options: nosniff` を付ける（`glance/main.py`）。

**Google の API を呼ぶとき**

- 利用者ごとに、更新トークンから作った認証情報（`google.oauth2.credentials.Credentials`）をメモリに持つ。アクセストークン（約1時間）が切れたら、ライブラリが自動で取り直す。
- 更新トークンが失効していたら（`invalid_grant`）、API は 401 と `{"code": "reauth_required"}` を返す。画面は「ログインし直してください」と出す。

## 5. トークンの暗号化

- Fernet（`cryptography`）で暗号化して DB に入れる。鍵は `/etc/glance/glance.env` の `GLANCE_TOKEN_KEY`。作り方は `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`（出てきた値を env に直接書き、どこにも貼らない）。
- 対象は、Google の更新トークン（`users.refresh_token_encrypted`）と Bing の API キー（`bing_keys.key_encrypted`）。
- 鍵を入れ替える手順（`glance/rekey.py`。本番では人が VPS で打つ）:
  1. 新しい鍵を作り、`GLANCE_TOKEN_KEY` を「新しい鍵,古い鍵」と並べて API を再起動する。暗号化は先頭の鍵で行い、復号は並べたどの鍵でもできる（`MultiFernet`）。
  2. `uv run python -m glance.rekey` で、古い鍵で暗号化した値を新しい鍵で暗号化し直す。どの鍵でも復号できない値が1つでもあれば、何も書き換えずに止める（古い鍵を並べ忘れたときに値を壊さないため）。表示するのは件数と行の ID だけで、値は出さない。
  3. `uv run python -m glance.rekey --check` で「古い鍵のまま 0件」になったら、`GLANCE_TOKEN_KEY` から古い鍵を外して再起動する。

## 6. API

`/api/auth/login`・`/api/auth/callback` 以外は、ログインが要る。サイトは、ログイン中の利用者の顧客（`tenant_id`）のものだけを扱う。

| メソッド・パス | 内容 |
|---|---|
| `GET /api/auth/login` | Google の同意画面へ送る（§4） |
| `GET /api/auth/callback` | Google から戻る。ログインを済ませて `/` へ |
| `POST /api/auth/logout` | セッションを消す |
| `GET /api/me` | ログイン中の利用者（メールアドレス）。未ログインなら 401 |
| `GET /api/ga4/properties` | ログインしたアカウントが見られる GA4 のプロパティの一覧（Admin API の `accountSummaries.list`）。アカウントごとにまとめ、追加済みかどうかも付ける |
| `GET /api/sites` | サイトの一覧（並び順）。各サイトは `{"id", "name", "ga4_property_id", "links"}`（並び順とタイムゾーンは DB にだけ持ち、返さない） |
| `POST /api/sites` | サイトを追加する。GA4 のプロパティ ID を受け取り、名前とタイムゾーンを Admin API の `properties.get` から取って入れる。GA4 の接続設定（`connections`）も作る |
| `PATCH /api/sites/{id}` | 名前・並び順を変える |
| `DELETE /api/sites/{id}` | サイトを消す（接続設定も消す） |
| `GET`・`PUT /api/sites/{id}/gsc`、`GET`・`POST /api/bing/keys`、`PUT /api/bing/keys/{id}`、`GET /api/bing/keys/{id}/sites`、`PUT /api/sites/{id}/bing` | Search Console・Bing の紐づけ（§6.4） |
| `GET /api/realtime` | 全サイトのリアルタイムを取る（§6.1） |
| `GET /api/demo/realtime` | デモ用のダミーの数字（§6.2）。ログイン不要 |
| `GET /api/seo` | 取り込んだ Search Console・Bing の数字（§6.5） |
| `GET /api/demo/seo` | SEO の画面のデモ用のダミーの数字（§6.3）。ログイン不要 |
| `GET /api/demo/sites`・`/api/demo/ga4/properties`・`/api/demo/sites/{id}/gsc`・`/api/demo/bing/keys`・`/api/demo/bing/keys/{id}/sites` | サイト設定のデモ用のダミー（§6.4）。ログイン不要 |

### 6.1 `GET /api/realtime`

- サイトごとに、[data_sources.md](data_sources.md) §5 の6回の呼び出しを行う。全サイト・全呼び出しを並行して行う（非同期のクライアント）。
- 1サイトの待ち時間の上限は10秒。超えたサイト、失敗したサイトは `status: "error"` にし、ほかのサイトの結果は返す。
- `minutesAgo` は値のない分を 0 で埋め、30分前から今までの30個にそろえる。
- 合計は返さない。画面で、選んだサイトを足して出す（[screen_design.md](screen_design.md) §3）。
- 上位のページは、サイトごとの上位20件だけを返す。全サイトをまとめた上位20件は、画面で選んだサイトに合わせて画面が並べ直す（[screen_design.md](screen_design.md) §3）。
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
      "per_minute": [
        {"minutes_ago": 29, "page_views": 3, "active_users": 2},
        {"minutes_ago": 28, "page_views": 5, "active_users": 4}
      ],
      "top_pages": [{"title": "記事のタイトル", "page_views": 12, "active_users": 8}],
      "devices": [{"key": "mobile", "active_users": 30}],
      "countries": [{"key": "JP", "active_users": 37}],
      "events": [{"name": "page_view", "event_count": 120}]
    },
    {"site_id": 2, "name": "TechShift", "status": "error", "error": "timeout"}
  ]
}
```

- `per_minute` は30個（例では途中を省いた）。
- `error` の種類: `timeout`（時間切れ）、`permission_denied`（プロパティを見る権限がない）、`quota`（上限に当たった）、`error`（その他）。

### 6.2 `GET /api/demo/realtime`

- ログイン不要。デモの画面（[screen_design.md](screen_design.md) §6）が使う。
- 手元とテストで使うフェイク（`glance/google/fake.py`）の数字を、`/api/realtime` と同じ集計（`fetch_realtime`）に通して返す。応答の形は §6.1 と同じ。サイトは「デモサイト A〜E」。
- DB・Google・利用者のデータには触れない（テストで確かめる）。だれが呼んでもダミーしか返らない。
- API にした理由（2026-11-26）: 項目を足すときはテストと手元の確認のためにフェイクも必ず直すので、デモがそのまま付いてくる。固定の JSON を画面に置く形だと、項目を足すたびに作り直しが要る。

### 6.3 `GET /api/demo/seo`

- ログイン不要。デモの SEO の画面（[screen_design.md](screen_design.md) §6・§7）が使う。本物の `GET /api/seo`（§6.5）と、引数・応答の形を同じにする（画面は取り元だけを変えて同じ部品を使う）。
- 応答の形は `glance/seo/schemas.py` のモデルで、本物とデモで共通。
- 数字は `glance/seo/demo.py` が、サイト・日付・期間から決まる形で作る（同じ条件なら同じ数字）。DB・Google・Bing・利用者のデータには触れない（テストで確かめる）。サイトは「デモサイト A〜E」。
- 期間と比べる期間の解釈は `glance/seo/periods.py`（[api_design.md](api_design.md) §1 と同じ。本物でも使う）。

引数:

| 名前 | 値 | 既定 |
|---|---|---|
| `engine` | `google` / `bing` | `google` |
| `period` | `last_7_days` / `last_28_days` / `this_month` / `last_month` / `custom` | `last_28_days` |
| `compare` | `previous_period` / `previous_year` / `none` | `previous_period` |
| `start`・`end` | `custom` のときの期間（`2026-11-01` の形）。終わりは、データがある最終日までに縮める | なし |

- 期間がおかしいとき（`custom` で始まり・終わりがない、始まりが終わりより後、始まりがデータのある最終日より後）は 400（`invalid_period`。`message` は画面にそのまま出せる文）。
- データがある最終日（`data_until`）: デモでは GSC は今日の3日前、Bing は前日（本物は取得ログから出す）。

応答の形（数字は例。配列は途中を省いた）:

```json
{
  "engine": "google",
  "period": {"start": "2026-10-27", "end": "2026-11-23"},
  "compare": {"start": "2026-09-29", "end": "2026-10-26"},
  "data_until": "2026-11-23",
  "sites": [
    {
      "site_id": 1,
      "name": "デモサイト A",
      "totals": {"clicks": 9846, "impressions": 385000, "position": 11.8},
      "compare_totals": {"clicks": 9758, "impressions": 381000, "position": 11.9},
      "daily": [{"date": "2026-10-27", "clicks": 390, "impressions": 14800, "position": 11.6}],
      "compare_daily": [{"date": "2026-09-29", "clicks": 330, "impressions": 13900, "position": 12.0}],
      "queries": [{"query": "RFID 課題", "clicks": 820, "impressions": 6022, "position": 1.5, "compare_clicks": 870}],
      "pages": [{"title": "記事のタイトル", "path": "/news/load-factor-trend", "clicks": 1947, "impressions": 13947, "position": 1.5, "compare_clicks": 944}],
      "crawl": null,
      "index": {"sitemap_urls": 3400, "sitemap_checked_at": "2026-11-23", "indexed": 2788, "pages_shown": 2856, "daily": [{"date": "2026-10-27", "pages": 1255}]}
    }
  ]
}
```

- 比べないとき（`compare=none`）は、`compare`・`compare_totals`・`compare_daily` が `null`、`compare_clicks` も `null`。
- `position` は表示回数の重みつき平均（[database_design.md](database_design.md) §6）。CTR は返さない（画面で「クリック ÷ 表示回数」を出す）。
- 合計は返さない。画面で、選んだサイトを足して出す（リアルタイムと同じ）。
- `period`・`compare` は実際の期間だけを返す（期間の名前は画面が持つ）。
- `queries`・`pages` は、サイトごとにクリックの多い順で100件まで。`compare_clicks` は、比べる期間のクリック。比べる期間に無いものは 0（本物と同じ）。
- `index` はインデックスの目安（§6.5）。
- Bing のとき: 日ごとの `position` は `null`（`totals` の `position` も `null`）。`queries` は空（今は取らない。[data_sources.md](data_sources.md) §4）。`crawl` に日ごとの `{"date", "crawled", "indexed", "errors"}` を入れる（`indexed` はその日の在庫なので足さない）。Google のときの `crawl` は `null`。

### 6.4 サイト設定の紐づけ（Search Console・Bing）と、デモの API

サイト設定は、GA4・Search Console・Bing の列を並べる。Search Console は、GA4 のプロパティを追加するときに一緒に紐づける（[screen_design.md](screen_design.md) §4）。紐づけは接続設定（`connections`）の行で持つ。行があれば紐づけていて、`target` が紐づけ先（サイトの URL）、同じ行にどの認証で呼ぶか（Google は利用者、Bing はキー）を持つ。Bing のキーは `bing_keys` に持つ（[database_design.md](database_design.md) §2）。紐づけを外しても取り込んだ数字は残す。紐づけ先を別のサイトに変えたら、前の先の数字と取得ログを消し、次の取り込みで新しい先の過去分から取る（取得ログの `target` で、前に取った先を見分ける。2026-11-28 コードレビューの対応）。コードは `glance/sites/links.py`（Search Console のサイトの選び方は `glance/sites/gsc.py`、Bing のキーの API は `glance/bing/routes.py`）。

**Search Console**

- `GET /api/sites` の各サイトに `links`（`{"gsc_site_url", "bing_site_url", "bing_key_id"}`。紐づけていなければ `null`）。
- `GET /api/ga4/properties` の、追加していないプロパティに `search_console`（`{"site_url": 同じドメインのサイト | null, "candidates": [見られるサイト]}`）。追加済みと、Search Console のサイトの一覧を取れないとき（API を有効にしていないなど）は `null`。このときも GA4 のプロパティの追加はできる。
- `POST /api/sites` に `gsc_site_url`（任意）。見られるサイトでなければ 400（`unknown_gsc_site`）で、サイトも作らない。
- `GET /api/sites/{id}/gsc`: `{"current", "suggested", "candidates"}`。`suggested` は同じドメインのサイト。
- `PUT /api/sites/{id}/gsc`: `{"site_url": "…" | null}`。`null` で外す（取り込んだ数字は残す）。接続設定は、保存した利用者の更新トークンで呼ぶ形にする。応答は 204（画面は保存の後に `GET /api/sites` を読み直す）。
- 同じドメインのサイトの選び方（`match_gsc_site`）: Admin API の `properties.dataStreams.list` でウェブのデータストリームのホストを取り、Search Console API の `sites.list`（確認していないサイトは除く）から選ぶ。ドメインのプロパティ（`sc-domain:`）を優先し（いくつか合うときは細かいほう）、なければ同じホスト（`www.` の有無は問わない）の URL のプロパティが1つだけのときに選ぶ（[data_sources.md](data_sources.md) §3）。
- Search Console API は REST（`https://www.googleapis.com/webmasters/v3/sites`）を httpx で呼ぶ。API を有効にしていないと 503（`gsc_api_disabled`）で、GCP のプロジェクトで有効にするよう出す。

**Bing**

- `GET /api/bing/keys`: 顧客のキーの一覧 `[{"id", "name", "last4"}]`。キーそのものは返さない。
- `POST /api/bing/keys`: `{"name", "key"}`。保存の前に `GetUserSites` を呼んで使えるキーか確かめる（使えなければ 400 `invalid_bing_key`）。同じ名前は 409（`name_taken`）。キーは Fernet で暗号化して入れる（§5 と同じ鍵）。
- `PUT /api/bing/keys/{id}`: `{"key"}`。入れ直し。そのキーを使う全サイトに効く。
- `GET /api/bing/keys/{id}/sites`: そのキーで見られる（確認済みの）サイトの URL。
- `PUT /api/sites/{id}/bing`: `{"key_id", "site_url"}`。キーで見られるサイトでなければ 400（`unknown_bing_site`）。`site_url` が `null` で外す（取り込んだ数字とキーは残す）。応答は 204。
- Bing の API はキーをクエリ文字列で送る仕様なので、URL をログ・エラーに出さない（httpx のログは WARNING 以上にし、通信の失敗は元の例外をつなげずに変換する）。

**デモ**（`/api/demo/sites`・`/api/demo/ga4/properties`・`/api/demo/sites/{id}/gsc`・`/api/demo/bing/keys`・`/api/demo/bing/keys/{id}/sites`。`glance/sites/demo.py`）

- ログイン不要。デモのサイト設定（[screen_design.md](screen_design.md) §6）が使う。応答の形は本物と同じ。
- サイトは「デモサイト A〜E」（`glance/google/fake.py` の `DEMO_SITES`）で、Search Console と Bing（キーは「デモのキー」1つ）を紐づけ済み。ドメインは `demo-a.example` など（`.example` は例のために取ってあるもので、実在しない）。プロパティは、その5つ（追加済み）と、未追加で Search Console のサイトが見つからない「デモサイト F」。
- 書き込みの API はない（デモのサイト設定は見るだけ）。DB・Google・Bing・利用者のデータには触れない（テストで確かめる）。

**手元・テスト**: フェイクモードでは、Search Console のサイトの一覧とデータストリームはダミー（`glance/google/fake.py`）、Bing は `FakeBingClient`（「bad」で始まるキーを使えないキーとする）。フェイクモードでも Bing のキーを保存するには `GLANCE_TOKEN_KEY` が要る。

### 6.5 取り込み（`python -m glance.sync`）と `GET /api/seo`

**取り込みのコマンド**（`glance/sync/`。全体は `runner.py`、Search Console は `gsc.py`、Bing は `bing.py`。VPS に出すまでは手元で打つ。[roadmap.md](roadmap.md) §3.1）

```
uv run python -m glance.sync                 # 紐づけた全サイトの GSC と Bing
uv run python -m glance.sync --source bing   # Bing だけ（gsc も選べる）
uv run python -m glance.sync --site 1        # サイトを絞る（何度でも）
```

- 接続先と鍵は `.env` から読む（API と同じ）。GSC は、紐づけた利用者の更新トークンで呼ぶ。Bing は、紐づけたキーで呼ぶ。
- **GSC**: 表（`gsc_site`・`gsc_page`・`gsc_query_page`）ごとに、取得済みの最終日の3日前から今日まで、1日ずつ取る。初めては16ヶ月前の月初から。1日分は消してから入れ直す。1回の取得は2.5万行までで、超える日は続きを取る。途中で失敗したら、その表はそこで止める（次回は取得済みの最終日から続ける。数字が1日もない期間（サイトを始める前など）は、前回までに取り終えた日から続ける）。サイトと表は並べて取るが、Search Console を同時に呼ぶのは3つまでにする（上限は利用者ごとに1分1,200回）。上限に当たったら（429、または 403 の `rateLimitExceeded` など）、15秒・30秒・60秒…と待って5回までやり直す。失敗したときは、API が返したエラーの文を取得ログに残す。
- **GSC のクエリの整理**: 取り込みの後に、翌月8日を過ぎた月のうち、今回取った月とまだ整理していない月について、その月の表示回数が10回未満のクエリを `gsc_query_page` から消す。整理した月は取得ログ（`gsc_query_cleanup`）に残す。クエリ表の取り込みが途中で失敗した回は整理しない（月の数字がそろっていないため。次回、取り終えてから整理する）。取れる最初の月（16ヶ月前）は、Search Console に月の途中からしか残っておらず月の数字がそろわないので整理しない。
- **サイトマップ**: GSC の表の後に、Search Console に登録したサイトマップ（`sitemaps.list`）を読み、載っている URL のパスで `sitemap_urls` を入れ替える（`glance/sync/sitemap.py`。索引はたどり、.gz も読む。上限はファイル500・URL 20万・1ファイル50MB）。サイトマップの取得は、サイトに直接 HTTP で行う。サーバーの内側に届かせないため、次のようにする（2026-11-28 コードレビュー・セキュリティレビューの対応）。
  - 紐づけた Search Console のサイトのドメインの外（ほかのサイト）は読まない。ポートは既定（80・443）だけ。転送先も1回ずつ確かめる。
  - つなぐ前に名前解決し、全部の IP が公開のもの（ループバック・プライベート・リンクローカル・予約・マルチキャストでない）ときだけ、確かめた IP にそのままつなぐ（ドメインの持ち主は名前を内側の IP に向けられるため。確かめた後に名前解決の結果を変えられても届かない）。https の証明書は元のホスト名で確かめる。環境変数のプロキシは使わない。
  - XML は木を作らずに先頭から読み、`loc` だけを拾う（壊れた・悪意のある大きなファイルでメモリを使いすぎないため）。実体（DTD の ENTITY）の宣言があれば読まない。登録が無い・読めない・ドメインの中に1つも無いときは失敗として取得ログに残し、前の URL のままにする。
- **Bing**: `GetRankAndTrafficStats`・`GetPageStats`・`GetCrawlStats` は日付を選べず、取れる範囲を全部返すので、毎回全部を上書きする（同じ日・週は書き換え）。
- **値のそろえ方**（[database_design.md](database_design.md) §7）: ページは URL をパスに（そろえて同じパスになった行は足し合わせる）、国は3文字を2文字に（分からない国は `(not set)`）、デバイスは小文字、Bing の日付は `/Date(…)/` を日付に。
- 表・ソースごとに取得ログ（`sync_runs`。取った先 `target` も）を残し、1行ずつ結果を出す。紐づけた利用者・キーを使えないとき（許可リストから外した人など）は、取らなかった表（サイトマップも）ごとに失敗を残す。1つのサイト・ソースで思わぬエラー（DB のエラーなど）が出ても、ほかは続ける。失敗があれば終了コードは 1。
- 1回目（2026-11-27、手元）: Bing は5サイトとも数秒で終わる。GSC の16ヶ月分は時間がかかる（API を1日1回ずつ呼ぶため）。最初は5サイト×3表を同時に呼んで上限に当たり、全部失敗した（エラーは 403）。同時に呼ぶ数を絞り、上限に当たったら待ってやり直す形にした。

**`GET /api/seo`**（`glance/seo/service.py`。ログインが要る。引数と応答の形は §6.3 のデモと同じ）

- サイトは、その検索エンジンを紐づけたものだけ（Google は Search Console、Bing は Bing）。
- `data_until` は取り込んだ数字がある最終日（GSC は `gsc_site`、Bing は `bing_site_daily` の最新の日）。まだ何も取り込んでいなければ `null` で、期間は既定の最終日（GSC は今日の3日前、Bing は前日）で決める。
- 合計と日ごとは `gsc_site`（Bing は `bing_site_daily`）から。期間の全部の日を並べ、数字のない日は 0 にする。掲載順位は表示回数の重みつき平均。
- クエリは `gsc_query_page`、ページは `gsc_page`（Bing は `bing_page_weekly`。週の日付が期間に入る週）を足し、サイトごとにクリックの多い順に100件。ページのタイトルは持っていないので `null`（GA4 の取り込みを作るまで。画面はパスを出す）。
- `compare_clicks`: 比べる期間に、そのサイトの数字が1日もなければ `null`（比べられない）。あれば、無いクエリ・ページは 0。
- サイトごとに `index`（インデックスの目安）を付ける: `{"sitemap_urls": サイトマップの URL 数 | null（まだ読めていない）, "sitemap_checked_at", "indexed", "pages_shown", "daily"}`。`indexed` は、Google は期間中に imp 1回以上のページのうちサイトマップにあるものの数（サイトマップを読めていなければ `null`）、Bing は `bing_crawl_daily` の期間の中で数字のある最後の日のインデックス数。`pages_shown`（サイトマップに無いものも含めた数）と `daily`（`[{"date", "pages"}]` 日ごとの検索に出たページ数）は Google だけで、Bing は `null`。デモも同じ形。
- Bing のクロールとインデックスは `bing_crawl_daily` から。期間の全部の日を並べ、数字のない日は `null`（インデックス数は在庫なので 0 にしない）。

## 7. 画面（Next.js）

- 静的書き出しで、ページは `/login`・`/`（リアルタイム）・`/seo`・`/settings/sites`・`/demo`（デモのリアルタイム）・`/demo/seo`（デモの SEO）・`/demo/settings/sites`（デモのサイト設定）の7つ。デモの3つはログイン不要。中身は [screen_design.md](screen_design.md)。
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
| `GLANCE_DATABASE_URL` | DB の接続 URI（パスワードが入る） |
| `GLANCE_TOKEN_KEY` | 更新トークンを暗号化する鍵（Fernet） |
| `GLANCE_GOOGLE_CLIENT_ID` | OAuth クライアントの ID |
| `GLANCE_GOOGLE_CLIENT_SECRET` | OAuth クライアントの秘密 |
| `GLANCE_ALLOWED_EMAILS` | ログインを許すメールアドレス（カンマ区切り） |
| `GLANCE_PUBLIC_URL` | 画面の URL。Google から戻る先（`/api/auth/callback`）を組み立てるのに使う |

Cloudflare Tunnel の認証情報は、cloudflared の設定ファイルとして別に置く（[infrastructure_design.md](infrastructure_design.md) §4）。

**秘密の値をログに出さない**（2026-11-28 セキュリティレビューの対応）

- 設定のうち `GLANCE_DATABASE_URL`・`GLANCE_TOKEN_KEY`・`GLANCE_GOOGLE_CLIENT_SECRET` は `SecretStr` で持ち、設定を表示しても値が出ないようにする（使うところでだけ取り出す）。
- API とコマンドの起動のときに、秘密を書き得るライブラリのログを WARNING 以上だけにする（`glance/logs.py`）。httpx（Bing のキーが URL に入る）、requests_oauthlib・oauthlib（DEBUG でクライアントの秘密・認可コード・更新トークンを書く）、google（Google の SDK は DEBUG で要求のヘッダーのアクセストークンを書く）。uvicorn のアクセスログは、ログインの戻り（`/api/auth/callback`）の URL の認可コードと state を伏せる。
- 運用の決まり: 本番でログの段階を DEBUG にしない。Google の SDK のログを開く環境変数（`GOOGLE_SDK_PYTHON_LOGGING_SCOPE`）を本番で設定しない。

## 10. 反映の手順

LeadHub と同じく、**手元で人がスクリプト（`scripts/deploy_prod.sh`）を実行する。** GitHub の main にあるコミットだけを出す。

1. **手元**: 出すコミットを一時ディレクトリに書き出し、そこで画面をビルドする（`npm ci`・`npm run build`）。コミットしていない変更が混ざらないようにするため。
2. **手元**: コードと書き出した画面を1つのアーカイブにして VPS へ送る。
3. **VPS**: リリースのディレクトリに展開する。uv で Python の環境を作り、`alembic upgrade head` を当てる。`current` を付け替えて `glance-api` を再起動する。
4. **戻し方**: `current` を前のリリースに付け替えて、再起動する。マイグレーションは自動では戻さない。

HTML は Cloudflare の既定ではキャッシュされず、JS・CSS はファイル名に中身のハッシュが入る。そのため、反映の後に Cloudflare のキャッシュを消す手順は要らない。

## 11. 手元での開発

手順は README の「手元で動かす」。

| 項目 | 内容 |
|---|---|
| DB | Glance 用の PostgreSQL 16 を Docker で立てる（`docker-compose.yml`。127.0.0.1:5434）。LeadHub の手元の DB とは別にする |
| API | uvicorn で 127.0.0.1:8101 |
| 画面 | `next dev` で localhost:3100。`/api` への要求を手元の FastAPI に中継する（開発サーバーのときだけの設定。静的書き出しでは中継が使えないため） |
| Google ログイン | OAuth クライアントの戻り先に、手元の URL（`http://localhost:3100/api/auth/callback`）も登録する。同意画面は「テスト」のままでよい（自分をテストユーザーに入れる。更新トークンは7日で切れる） |
| フェイクモード | `GLANCE_FAKE_GOOGLE=1` で、Google を使わずに動かす。ログインは許可リストの最初のメールアドレスになり、GA4 はダミーの数字を返す（`glance/google/fake.py`）。ダミーのプロパティのうち「エラー確認用」は、リアルタイムが必ず時間切れになる。`GLANCE_PUBLIC_URL` が手元の URL でないと起動しない |
| テスト | API は pytest（手元の DB コンテナに `glance_test` を作って使う）。Google・Bing の呼び出しは、フェイクや差し替えたクライアントで試す。画面は `tests/e2e/`（Playwright。フェイクモードの API と書き出した画面をテストの中で起動し、デモ・連携・取り込み・SEO の流れをブラウザで確かめる）。ブラウザが要るので `GLANCE_E2E=1` のときだけ動かす（ふだんの `uv run pytest` では飛ばす） |
