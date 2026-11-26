const numberFormat = new Intl.NumberFormat("ja-JP");

export function formatNumber(value: number): string {
  return numberFormat.format(value);
}

// 軸の目盛り。1万を超えたら「1.2万」の形にする（docs/01_design/design_guideline.md §5）
export function formatAxis(value: number): string {
  if (Math.abs(value) >= 10000) {
    return `${Number((value / 10000).toFixed(1))}万`;
  }
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

// サイトの色。並び順に --series-1〜8 を割り当て、9サイト目からは灰色の「その他」（色は作らない。同 §2.2）
export const SERIES_COUNT = 8;

export function siteColor(index: number): string {
  return index < SERIES_COUNT ? `var(--series-${index + 1})` : "var(--series-other)";
}
