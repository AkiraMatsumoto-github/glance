const numberFormat = new Intl.NumberFormat("ja-JP");

export function formatNumber(value: number): string {
  return numberFormat.format(value);
}

// 時刻は日本時間で出す（docs/01_design/screen_design.md §1）
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("ja-JP", {
    timeZone: "Asia/Tokyo",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

// サイトの色。並び順に --chart-1〜5 を割り当てる（6サイト目からは繰り返す）
export function siteColor(index: number): string {
  return `var(--chart-${(index % 5) + 1})`;
}
