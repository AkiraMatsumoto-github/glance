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

**更新トークンがもらえないとき**: Google は、2回目以降の同意では更新トークンを返さない。戻ってきたときに更新トークンがなく、保存済みのものもないときは、`prompt=consent` を付けてもう一度同意画面へ送る。保存済みの更新トークンが失効したとき（API が `reauth_required` を返したとき）は、ログイン画面のボタンが `prompt=consent` 付きになり、同意画面を出してもらい直す。

**セッション**

- ランダムな ID をクッキー（`HttpOnly`・`Secure`・`SameSite=Lax`）に入れる。DB（`sessions`）には ID のハッシュだけを入れる。
- 期限は30日。ログアウトで消す。
- 書き込みの要求（POST・PATCH・DELETE）は JSON だけを受ける。`SameSite=Lax` と合わせて、別のサイトからの書き込み（CSRF）を防ぐ。

**Google の API を呼ぶとき**

- 利用者ごとに、更新トークンから作った認証情報（`google.oauth2.credentials.Credentials`）をメモリに持つ。アクセストークン（約1時間）が切れたら、ライブラリが自動で取り直す。
- 更新トークンが失効していたら（`invalid_grant`）、API は 401 と `{"code": "reauth_required"}` を返す。画面は「ログインし直してください」と出す。

## 5. トークンの暗号化

- Fernet（`cryptography`）で暗号化して DB に入れる。鍵は `/etc/glance/glance.env` の `GLANCE_TOKEN_KEY`。作り方は `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`（出てきた値を env に直接書き、どこにも貼らない）。
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
| `GET /api/realtime` | 全サイトのリアルタイムを取る（§6.1） |
| `GET /api/demo/realtime` | デモ用のダミーの数字（§6.2）。ログイン不要 |
| `GET /api/demo/seo` | SEO の画面のデモ用のダミーの数字（§6.3）。ログイン不要 |
| `GET /api/demo/sites`・`/api/demo/ga4/properties`・`/api/demo/gsc/sites`・`/api/demo/bing/sites` | サイト設定のデモ用のダミー（§6.4）。ログイン不要 |

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

- ログイン不要。デモの SEO の画面（[screen_design.md](screen_design.md) §6・§7）が使う。2番目の段階で作る本物の `GET /api/seo` と、引数・応答の形を同じにする（画面は取り元だけを変えて同じ部品を使う）。
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
  "period": {"name": "last_28_days", "label": "直近28日", "start": "2026-10-27", "end": "2026-11-23"},
  "compare": {"name": "previous_period", "start": "2026-09-29", "end": "2026-10-26"},
  "data_until": "2026-11-23",
  "sites": [
    {
      "site_id": 1,
      "name": "デモサイト A",
      "status": "ok",
      "totals": {"clicks": 9846, "impressions": 385000, "position": 11.8},
      "compare_totals": {"clicks": 9758, "impressions": 381000, "position": 11.9},
      "daily": [{"date": "2026-10-27", "clicks": 390, "impressions": 14800, "position": 11.6}],
      "compare_daily": [{"date": "2026-09-29", "clicks": 330, "impressions": 13900, "position": 12.0}],
      "queries": [{"query": "RFID 課題", "clicks": 820, "impressions": 6022, "position": 1.5, "compare_clicks": 870}],
      "pages": [{"title": "記事のタイトル", "path": "/news/load-factor-trend", "clicks": 1947, "impressions": 13947, "position": 1.5, "compare_clicks": 944}],
      "crawl": null
    }
  ]
}
```

- 比べないとき（`compare=none`）は、`compare`・`compare_totals`・`compare_daily` が `null`、`compare_clicks` も `null`。
- `position` は表示回数の重みつき平均（[database_design.md](database_design.md) §6）。CTR は返さない（画面で「クリック ÷ 表示回数」を出す）。
- 合計は返さない。画面で、選んだサイトを足して出す（リアルタイムと同じ）。
- `queries`・`pages` は、サイトごとにクリックの多い順で100件まで。`compare_clicks` は、比べる期間のクリック。比べる期間の100件に入っていないものは `null`。
- Bing のとき: 日ごとの `position` は `null`（`totals` の `position` も `null`）。`queries` は空（今は取らない。[data_sources.md](data_sources.md) §4）。`crawl` に日ごとの `{"date", "crawled", "indexed", "errors"}` を入れる（`indexed` はその日の在庫なので足さない）。Google のときの `crawl` は `null`。

### 6.4 サイト設定の紐づけと、デモの API

サイト設定は、GA4・Search Console・Bing の列を並べる。Search Console は、GA4 のプロパティを追加するときに一緒に紐づける（[screen_design.md](screen_design.md) §4）。画面はデモで先に作った（2026-11-27）。

**応答の形**（本物とデモで同じ）

- `GET /api/sites` の各サイトに `links`（`{"gsc_site_url": "sc-domain:…" | null, "bing_site_url": "https://…/" | null}`）。紐づけの API があるときだけ入れる。本物は、紐づけの保存（下）を作るまで `null` を返し、画面は Search Console・Bing の列を出さない。
- `GET /api/ga4/properties` の各プロパティに `search_console`（`{"site_url": 同じドメインのサイト | null, "candidates": [選べるサイト]}`）。追加済みのプロパティは `null`。本物は、作るまで `null`。
- `GET /api/gsc/sites`: ログインしたアカウントが見られる Search Console のサイトの一覧（`["sc-domain:…", "https://…/"]`）。
- `GET /api/bing/sites`: `{"key_saved": true, "sites": ["https://…/"]}`。保存済みの API キーで見られる Bing のサイト。キーそのものは返さない。

**デモ**（`/api/demo/sites`・`/api/demo/ga4/properties`・`/api/demo/gsc/sites`・`/api/demo/bing/sites`。`glance/sites/demo.py`）

- ログイン不要。デモのサイト設定（[screen_design.md](screen_design.md) §6）が使う。
- サイトは「デモサイト A〜E」（`glance/google/fake.py` の `DEMO_SITES`）で、Search Console と Bing を紐づけ済み。ドメインは `demo-a.example` など（`.example` は例のために取ってあるもので、実在しない）。プロパティは、その5つ（追加済み）と、未追加で Search Console のサイトが見つからない「デモサイト F」。
- 書き込みの API はない（デモのサイト設定は見るだけ）。DB・Google・Bing・利用者のデータには触れない（テストで確かめる）。

**本物で作るもの**（[roadmap.md](roadmap.md) §3.1）

- `connections` に紐づけ先の列（Search Console のサイト URL・Bing のサイト URL）を足す。Bing の API キーは利用者ごとに1つで、暗号化して持つ（[database_design.md](database_design.md) §2）。
- 同じドメインの Search Console のサイトを選ぶ: GA4 の Admin API でプロパティのウェブのデータストリームの URL を取り（`properties.dataStreams.list`）、Search Console API のサイト一覧（`sites.list`）から、`sc-domain:そのドメイン` かそのドメインの URL のサイトを探す。1つだけ見つかったときに選んでおく。
- 書き込み: サイトの追加で Search Console のサイトも受け取る、Search Console・Bing の紐づけの保存、Bing の API キーの保存（入れ直し）と「見る」。

## 7. 画面（Next.js）

- 静的書き出しで、ページは `/login`・`/`（リアルタイム）・`/settings/sites`・`/demo`（デモのリアルタイム）・`/demo/seo`（デモの SEO）・`/demo/settings/sites`（デモのサイト設定）の6つ。デモの3つはログイン不要。中身は [screen_design.md](screen_design.md)。
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

手順は README の「手元で動かす」。

| 項目 | 内容 |
|---|---|
| DB | Glance 用の PostgreSQL 16 を Docker で立てる（`docker-compose.yml`。127.0.0.1:5434）。LeadHub の手元の DB とは別にする |
| API | uvicorn で 127.0.0.1:8101 |
| 画面 | `next dev` で localhost:3100。`/api` への要求を手元の FastAPI に中継する（開発サーバーのときだけの設定。静的書き出しでは中継が使えないため） |
| Google ログイン | OAuth クライアントの戻り先に、手元の URL（`http://localhost:3100/api/auth/callback`）も登録する。同意画面は「テスト」のままでよい（自分をテストユーザーに入れる。更新トークンは7日で切れる） |
| フェイクモード | `GLANCE_FAKE_GOOGLE=1` で、Google を使わずに動かす。ログインは許可リストの最初のメールアドレスになり、GA4 はダミーの数字を返す（`glance/google/fake.py`）。ダミーのプロパティのうち「エラー確認用」は、リアルタイムが必ず時間切れになる。`GLANCE_PUBLIC_URL` が手元の URL でないと起動しない |
| テスト | API は pytest（手元の DB コンテナに `glance_test` を作って使う）。Google の呼び出しは、フェイクや差し替えたクライアントで試す |
