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
// key は deviceCategory の値（mobile など）か、countryId（JP など）
export type BreakdownRow = { key: string; page_views: number; active_users: number };

export type RealtimeErrorKind = "timeout" | "permission_denied" | "quota" | "error";

export type RealtimeSite =
  | {
      site_id: number;
      name: string;
      status: "ok";
      last_30_min: Totals;
      last_5_min: Totals;
      per_minute: MinuteRow[];
      top_pages: PageRow[];
      devices: BreakdownRow[];
      countries: BreakdownRow[];
    }
  | { site_id: number; name: string; status: "error"; error: RealtimeErrorKind };

export type OkSite = Extract<RealtimeSite, { status: "ok" }>;

export type Realtime = {
  fetched_at: string;
  sites: RealtimeSite[];
  total: { last_30_min: Totals; last_5_min: Totals };
};

export type Metric = "page_views" | "active_users";
