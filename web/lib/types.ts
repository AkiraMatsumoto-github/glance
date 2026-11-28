// API の応答の型（docs/01_design/technical_design.md §6）

export type Me = { email: string };

// Search Console・Bing の紐づけ先と、Bing で使うキー。紐づけていないものは null
export type SiteLinks = { gsc_site_url: string | null; bing_site_url: string | null; bing_key_id: number | null };

export type Site = {
  id: number;
  name: string;
  ga4_property_id: string | null;
  links: SiteLinks;
};

// GA4 のプロパティと同じドメインの Search Console のサイト（見つからなければ null）と、選べるサイト
export type SearchConsoleMatch = { site_url: string | null; candidates: string[] };
export type GaProperty = {
  property_id: string;
  name: string;
  added: boolean;
  // 追加済みのとき・Search Console のサイトの一覧を取れないとき（API を有効にしていないなど）は null
  search_console: SearchConsoleMatch | null;
};
// サイトの Search Console の紐づけ先（current）、同じドメインのサイト（suggested）、選べるサイト
export type GscChoice = { current: string | null; suggested: string | null; candidates: string[] };
// Bing の API キー。キーそのものは返らず、名前と末尾4文字だけ
export type BingKey = { id: number; name: string; last4: string };
export type GaAccount = { account_id: string; name: string; properties: GaProperty[] };

export type Totals = { page_views: number; active_users: number; key_events: number };
export type MinuteRow = { minutes_ago: number; page_views: number; active_users: number };
export type PageRow = { title: string; page_views: number; active_users: number };
// key は deviceCategory の値（mobile など）か、countryId（JP など）。ユーザーの属性なので UU だけ
export type BreakdownRow = { key: string; active_users: number };
export type EventRow = { name: string; event_count: number };

export type RealtimeErrorKind = "timeout" | "permission_denied" | "quota" | "error";

export type RealtimeSite =
  | {
      site_id: number;
      name: string;
      status: "ok";
      last_30_min: Totals;
      per_minute: MinuteRow[];
      top_pages: PageRow[];
      devices: BreakdownRow[];
      countries: BreakdownRow[];
      events: EventRow[];
    }
  | { site_id: number; name: string; status: "error"; error: RealtimeErrorKind };

export type OkSite = Extract<RealtimeSite, { status: "ok" }>;

export type Realtime = {
  fetched_at: string;
  sites: RealtimeSite[];
};

export type Metric = "page_views" | "active_users";

// SEO（docs/01_design/technical_design.md §6.3）。Google と Bing で同じ形。Bing は掲載順位が null、クエリが空
export type SeoEngine = "google" | "bing";
export type SeoPeriodName = "last_7_days" | "last_28_days" | "this_month" | "last_month" | "custom";
export type SeoCompareName = "previous_period" | "previous_year" | "none";

export type SeoTotals = { clicks: number; impressions: number; position: number | null };
export type SeoDay = SeoTotals & { date: string };
// compare_clicks は、比べる期間のクリック。比べないとき・比べる期間に数字がないときは null。
// position は、表示回数の重みつき平均（Bing で順位が分からないものは null）
type SeoItem = { clicks: number; impressions: number; position: number | null; compare_clicks: number | null };
export type SeoQuery = SeoItem & { query: string };
// 本物はページのタイトルを持っていない（GA4 の取り込みを作るまで null。パスを出す）
export type SeoPage = SeoItem & { title: string | null; path: string };
// indexed はその日のインデックス数（在庫なので足さない）。数字のない日は null
export type CrawlDay = { date: string; crawled: number | null; indexed: number | null; errors: number | null };

// インデックスの目安。サイトマップの URL 数（まだ読めていなければ null）と並べる。
// indexed は、Google は期間中に検索に1回でも出た（imp 1回以上の）ページのうちサイトマップにあるものの数
// （サイトマップを読めていなければ null）、Bing は Bing のインデックス数（期間の最後の日）。
// pages_shown（サイトマップに無いものも含めた数）と daily（日ごとの検索に出たページ数）は Google だけ
export type SeoIndex = {
  sitemap_urls: number | null;
  sitemap_checked_at: string | null;
  indexed: number | null;
  pages_shown: number | null;
  daily: { date: string; pages: number }[] | null;
};

export type SeoSite = {
  site_id: number;
  name: string;
  totals: SeoTotals;
  compare_totals: SeoTotals | null;
  daily: SeoDay[];
  compare_daily: SeoDay[] | null;
  queries: SeoQuery[];
  pages: SeoPage[];
  crawl: CrawlDay[] | null;
  index: SeoIndex;
};

export type Seo = {
  engine: SeoEngine;
  period: { start: string; end: string };
  compare: { start: string; end: string } | null; // 比べないときは null
  data_until: string | null; // 取り込んだ数字がある最終日。まだ何も取り込んでいなければ null
  sites: SeoSite[];
};
