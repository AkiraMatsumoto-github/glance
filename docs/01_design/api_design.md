# glance 集計 API 設計

集計の指定（問い合わせ指定）を検証し、SQL に変換して結果を返す部分の設計。AI と画面（ダッシュボードの再集計）の両方がこの指定を使う。AI がこの指定をどう作るかは [ai_query_design.md](ai_query_design.md)、テーブルは [database_design.md](database_design.md)。

管理コンソール向けの HTTP エンドポイント（チャット、ダッシュボード、サイト設定）は未設計。

---

## 1. 問い合わせ指定

```json
{
  "source": "ga4",
  "metrics": ["sessions"],
  "dimensions": ["date", "channel"],
  "filters": [{"dimension": "channel", "op": "in", "values": ["Organic Search", "Referral"]}],
  "period": {"preset": "this_month"},
  "compare": "previous_period",
  "sort": {"metric": "sessions", "order": "desc"},
  "limit": 50
}
```

- `source`: `ga4` / `gsc` / `bing`。1つの指定は1つのソースだけを対象にする。
- `metrics` / `dimensions` は、そのソースの一覧（付録）の ID から選ぶ。時間の軸は `date` / `week` / `month`。
- `period`: `this_month` / `last_month` / `this_week` / `last_week` / `last_7_days` / `last_28_days`、または `{"start": "...", "end": "..."}`。週は月曜始まり。「今日」は日本時間で決める。
  - 期間の終わりは、そのソースのデータがある最終日までにする。`last_7_days` / `last_28_days` も、データがある最終日から数える。例: 11/10 に GSC で `this_month` → 11/1〜11/7。
  - 画面と AI には、この実際に集計した期間を出す・渡す。
- `compare`: `previous_period` / `previous_year` / なし。
  - `previous_period`: `this_month` / `last_month` は前の月の全体、`this_week` / `last_week` は前の週の全体、`last_7_days` / `last_28_days` / 日付指定は直前の同じ日数。
  - `previous_year`: 前年の同じ日付。
- `exclusions`（省略可）: 適用する除外設定の ID の一覧。省略したらサイトの既定を使う。AI は、利用者が「ボットも含めて」のように頼んだときだけ指定する。
- サイト ID は指定に含めない。サーバーがログイン中のサイトから付ける。

## 2. サーバーの処理

1. **検証する。** 指標・軸がそのソースの一覧にあるか、1つのテーブルにそろうかを確かめる。そろわなければ、出せない理由と、出せる組み合わせを返す。
2. **テーブルを選ぶ。** 指定のソースのテーブルで、指定の軸をすべて含むもののうち、軸の数が最も少ないものを使う。
   - 軸が日付だけなら `ga4_totals`。
   - UTM の表でチャネルが要るときは、`ga4_channel_map` でつなぐ。
   - ユーザー数は `ga4_users` のみ。期間が日・週・月の単位に合うときはその値を使い、合わなければ日ごとの値を足した延べ人数にする（[database_design.md](database_design.md) の集計のルール）。
3. **SQL を組み立てる。**
   - パラメータ付きで組み立て、サイト ID の条件を必ず付ける。
   - 除外設定を `WHERE` の条件として加える。対象の列がない表（例: ランディングページのない `ga4_pages`）では、その除外は適用されない。そのことを結果に含める。
4. **比較する。** `compare` があれば比較期間でも同じ集計をし、差と増減率をサーバーで計算する。
5. **返す。** 行、条件（実際に集計した期間・軸・適用した除外）、該当するデータ注記を返す。

## 3. 表示のルール

- 日付軸があれば折れ線グラフ。内訳が多いときは上位5件と「その他」にまとめる（表には全件出す）。
- 日付軸がなければ表と横棒グラフ（上位20件）。
- 国・地域で集計した表では、最後に `(重複調整)` 行を出して合計を合わせる。グラフ・上位の件数・順位には入れない。
- ユーザー数を延べ人数で出したときは「延べ」と表示する。
- グラフの下に、条件（実際に集計した期間を含む）・適用した除外・データ注記を必ず出す。

## 4. 除外設定

- サイトごとに `site_exclusions` で定義する。条件に使えるのは、各表が持つ列（言語、ランディングページ、国など）。
- それぞれに「既定でオンか」を持たせる。結果カードでオン/オフを切り替えられ、ピン留めすると切り替えた状態も保存する。
- すべてオフにすると、GA4 の画面とほぼ同じ数字になる（[database_design.md](database_design.md) の集計のルールにある差を除く）。
- 外販先の顧客は、除外設定なしで始める。

## 5. LogiShift の初期設定

### 5.1 除外設定（`site_exclusions`、どちらも既定でオン）

| 名前 | 条件 | 理由 |
|---|---|---|
| ボット | 言語が `Japanese` 以外を除く | GA4 は既知のボットを自動で除くが、LogiShift に来ているボットは対象外。言語が日本語以外のユーザーが約3割（10/6〜11/5）。中国語のユーザーは全員1PV・平均12秒（11/5） |
| ランディングページなし | ランディングページが `(not set)` のセッションを除く | ページを見ていないセッション。gtag.js の頃からセッションの約1割あった GA4 共通の現象で、Zaraz への切り替え後は11.5% |

### 5.2 データ注記（`data_notes`）

注記の形は未決（[database_design.md](database_design.md) の未決事項）。

| 対象 | 期間 | 注記 |
|---|---|---|
| GA4 国・地域 | 2026-09-26〜 | 信頼できない。日本語ユーザーの PV の22%が米国と判定されている（Zaraz の IP を隠す設定が原因とみられる。未確認） |
| GA4 ユーザー数・新規/リピーター | 2026-09-26 をまたぐ期間 | Zaraz への切り替えでユーザー ID が振り直され、全員が新規扱いになった。この日をまたぐ比較はできない |
| GA4 イベント（scroll） | 2026-09-26〜 | 拡張計測の scroll が Zaraz への切り替え後 0 になっている |
| Bing 日次 | 常時 | 曜日差が大きい（金・土が低い）。直近2〜3日は確定していない |

---

## 付録: 指標・軸の ID と各ソースの項目名

問い合わせ指定（§1）では、`source` ごとに下の ID を使う。値の形は [database_design.md](database_design.md) の値のそろえ方。

時間の軸 `date` / `week` / `month` は全ソース共通。`week`・`month` は `date` からサーバーで作る（週は月曜始まり）。ただし Bing のページ別は週単位のデータしかない。

### GA4（`source: "ga4"`）

| 種類 | ID | 表示名 | GA4 の項目名 |
|---|---|---|---|
| 軸 | `date` | 日付 | `date` |
| 軸 | `channel` | チャネル | `sessionDefaultChannelGroup` |
| 軸 | `utm_source` | 参照元（utm_source） | `sessionSource` |
| 軸 | `utm_medium` | メディア（utm_medium） | `sessionMedium` |
| 軸 | `utm_campaign` | キャンペーン（utm_campaign） | `sessionCampaignName` |
| 軸 | `utm_term` | UTM term | `sessionManualTerm` |
| 軸 | `utm_content` | UTM content | `sessionManualAdContent` |
| 軸 | `device` | デバイス | `deviceCategory` |
| 軸 | `new_vs_returning` | 新規/リピーター | `newVsReturning` |
| 軸 | `language` | 言語 | `language` |
| 軸 | `country` / `region` | 国 / 地域 | `countryId` / `region` |
| 軸 | `landing_page` | ランディングページ | `landingPage` |
| 軸 | `page` | ページ | `pagePath` |
| 軸 | `item_id` / `item_name` / `item_category` | 商品 ID / 商品名 / 商品カテゴリ | `itemId` / `itemName` / `itemCategory` |
| 軸 | `event_name` | イベント名 | `eventName` |
| 指標 | `sessions` | セッション | `sessions` |
| 指標 | `engaged_sessions` | エンゲージのあったセッション | `engagedSessions` |
| 指標 | `page_views` | PV | `screenPageViews` |
| 指標 | `engagement_time` | エンゲージメント時間 | `userEngagementDuration` |
| 指標 | `key_events` | キーイベント | `keyEvents` |
| 指標 | `revenue` | 売上 | `purchaseRevenue` |
| 指標 | `purchases` | 購入数 | `transactions` |
| 指標 | `add_to_carts` | カート投入数 | `addToCarts` |
| 指標 | `checkouts` | チェックアウト開始数 | `checkouts` |
| 指標 | `item_views` / `item_add_to_carts` / `item_purchases` / `item_revenue` | 商品の閲覧数 / カート投入数 / 購入数 / 売上 | `itemsViewed` / `itemsAddedToCart` / `itemsPurchased` / `itemRevenue` |
| 指標 | `event_count` | イベント数 | `eventCount` |
| 指標 | `users` / `new_users` / `active_users` | ユーザー数 / 新規ユーザー数 / アクティブユーザー数 | `totalUsers` / `newUsers` / `activeUsers` |
| 指標（計算） | `engagement_rate` | エンゲージメント率 | `engaged_sessions` ÷ `sessions` |
| 指標（計算） | `engagement_time_per_session` | セッションあたりエンゲージメント時間 | `engagement_time` ÷ `sessions` |

### GSC（`source: "gsc"`）

| 種類 | ID | 表示名 | GSC の項目名 |
|---|---|---|---|
| 軸 | `date` | 日付 | `date` |
| 軸 | `query` | クエリ | `query` |
| 軸 | `page` | ページ | `page` |
| 軸 | `device` | デバイス | `device` |
| 軸 | `country` | 国 | `country` |
| 指標 | `clicks` | クリック | `clicks` |
| 指標 | `impressions` | 表示回数 | `impressions` |
| 指標（計算） | `ctr` | CTR | `clicks` ÷ `impressions` |
| 指標（計算） | `position` | 掲載順位 | Σ(`position`×`impressions`) ÷ Σ`impressions` |

### Bing（`source: "bing"`）

| 種類 | ID | 表示名 | Bing の項目名 |
|---|---|---|---|
| 軸 | `date` | 日付 | `Date` |
| 軸 | `page` | ページ（上位100ページのみ、週単位） | `GetPageStats` の `Query`（URL が入る） |
| 指標 | `clicks` | クリック | `Clicks` |
| 指標 | `impressions` | 表示回数 | `Impressions` |
| 指標（計算） | `ctr` | CTR | `clicks` ÷ `impressions` |
| 指標 | `position` | 平均掲載順位（ページ別のみ） | `AvgImpressionPosition` |
| 指標 | `crawled_pages` | クロール数 | `CrawledPages` |
| 指標 | `indexed_pages` | インデックス数（期間末の値） | `InIndex` |
| 指標 | `backlinks` | 被リンク数（期間末の値） | `InLinks` |
| 指標 | `crawl_errors` | クロールエラー | `CrawlErrors` |
