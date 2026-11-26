import { ShareBars, type Category } from "@/components/realtime/share-bars";
import type { OkSite } from "@/lib/types";

// デバイス・国の内訳（docs/01_design/screen_design.md §3）。どちらもユーザーの属性なので、直近30分の UU の割合

const DEVICE_LABELS: Record<string, string> = { mobile: "スマホ", desktop: "PC", tablet: "タブレット" };
const DEVICES: Category[] = [
  { key: "mobile", label: "スマホ" },
  { key: "desktop", label: "PC" },
  { key: "tablet", label: "タブレット" },
  { key: "other", label: "その他" }, // smart tv など
];

export function DeviceBars({ sites, colors }: { sites: OkSite[]; colors: Map<number, string> }) {
  return (
    <ShareBars
      title="デバイス（UU の割合）"
      sites={sites}
      colors={colors}
      categories={DEVICES}
      categoryOf={(key) => (key in DEVICE_LABELS ? key : "other")}
      rowsOf={(site) => site.devices}
    />
  );
}

const TOP_COUNTRIES = 3;
const regionNames = new Intl.DisplayNames(["ja"], { type: "region" });

function countryLabel(code: string): string {
  if (!/^[A-Z]{2}$/.test(code)) return "不明"; // (not set) など
  return regionNames.of(code) ?? code;
}

// 選んだサイトを合わせて UU の多い3か国を出し、残りは「その他」。どのサイトの帯も同じ区分・同じ濃さにする
export function CountryBars({ sites, colors }: { sites: OkSite[]; colors: Map<number, string> }) {
  const totals = new Map<string, number>();
  for (const site of sites) {
    for (const row of site.countries) totals.set(row.key, (totals.get(row.key) ?? 0) + row.active_users);
  }
  const top = [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_COUNTRIES)
    .map(([key]) => key);
  const categories: Category[] = [...top.map((key) => ({ key, label: countryLabel(key) })), { key: "other", label: "その他" }];

  return (
    <ShareBars
      title="国（UU の割合）"
      note="Zaraz で GA4 を入れているサイトでは、日本の読者の一部がアメリカ合衆国などと判定されます（LogiShift では日本語の読者の PV の22%）。アメリカ合衆国の割合は、実際より多く出ます。"
      sites={sites}
      colors={colors}
      categories={categories}
      categoryOf={(key) => (top.includes(key) ? key : "other")}
      rowsOf={(site) => site.countries}
    />
  );
}
