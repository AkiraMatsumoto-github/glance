// API の応答の型（docs/01_design/technical_design.md §6）

export type Me = { email: string };

export type Site = {
  id: number;
  name: string;
  sort_order: number;
  timezone: string;
  ga4_property_id: string | null;
};

export type GaProperty = { property_id: string; name: string; added: boolean };
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
// compare_clicks は、比べる期間のクリック。比べないとき・比べる期間の上位に入っていないときは null
type SeoItem = { clicks: number; impressions: number; position: number; compare_clicks: number | null };
export type SeoQuery = SeoItem & { query: string };
export type SeoPage = SeoItem & { title: string; path: string };
// indexed はその日のインデックス数（在庫なので足さない）
export type CrawlDay = { date: string; crawled: number; indexed: number; errors: number };

export type SeoSite = {
  site_id: number;
  name: string;
  status: "ok";
  totals: SeoTotals;
  compare_totals: SeoTotals | null;
  daily: SeoDay[];
  compare_daily: SeoDay[] | null;
  queries: SeoQuery[];
  pages: SeoPage[];
  crawl: CrawlDay[] | null;
};

export type Seo = {
  engine: SeoEngine;
  period: { name: SeoPeriodName; label: string; start: string; end: string };
  compare: { name: SeoCompareName; start: string; end: string } | null;
  data_until: string;
  sites: SeoSite[];
};
