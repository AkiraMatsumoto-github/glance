const numberFormat = new Intl.NumberFormat("ja-JP");

export function formatNumber(value: number): string {
  return numberFormat.format(value);
}

// 軸の目盛りと、カードの表示回数。1万を超えたら「1.2万」の形にする（docs/01_design/design_guideline.md §5）
export function formatCompact(value: number): string {
  if (Math.abs(value) >= 10000) {
    return `${Number((value / 10000).toFixed(1))}万`;
  }
  return numberFormat.format(value);
}

// 割合（0.026 → 2.6%）
export function formatPercent(ratio: number, digits = 1): string {
  return `${(ratio * 100).toFixed(digits)}%`;
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

// 日付（2026-11-23）。API の日付は、その日そのもの（時刻もタイムゾーンもない）なので、Date にせず文字のまま分ける
function dateParts(isoDate: string): { year: number; month: number; day: number; weekday: string } {
  const [year, month, day] = isoDate.split("-").map(Number);
  const weekday = "日月火水木金土"[new Date(Date.UTC(year, month - 1, day)).getUTCDay()];
  return { year, month, day, weekday };
}

// 軸の目盛り（11/23）
export function formatShortDate(isoDate: string): string {
  const { month, day } = dateParts(isoDate);
  return `${month}/${day}`;
}

// 文の中の日付（11月23日）。年・曜日は、要るところだけ付ける
export function formatDate(isoDate: string, { year = false, weekday = false } = {}): string {
  const p = dateParts(isoDate);
  return `${year ? `${p.year}年` : ""}${p.month}月${p.day}日${weekday ? `（${p.weekday}）` : ""}`;
}

// 期間（2026年10月27日〜11月23日）。終わりの年は、始まりと違うときだけ書く
export function formatRange(start: string, end: string): string {
  const sameYear = start.slice(0, 4) === end.slice(0, 4);
  return `${formatDate(start, { year: true })}〜${formatDate(end, { year: !sameYear })}`;
}

// 期間の日数（両端を含む）
export function countDays(start: string, end: string): number {
  const utc = (iso: string) => {
    const { year, month, day } = dateParts(iso);
    return Date.UTC(year, month - 1, day);
  };
  return (utc(end) - utc(start)) / 86_400_000 + 1;
}

// サイトの色。並び順に --series-1〜8 を割り当て、9サイト目からは灰色の「その他」（色は作らない。同 §2.2）
export const SERIES_COUNT = 8;

export function siteColor(index: number): string {
  return index < SERIES_COUNT ? `var(--series-${index + 1})` : "var(--series-other)";
}
