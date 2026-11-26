// リアルタイムの注記（docs/01_design/data_sources.md §5「画面の注記」）。いつも出し、長い部分は「詳しく」で開く
export function RealtimeNotes() {
  return (
    <details className="rounded-xl border bg-surface px-4 py-2.5 text-ink-2">
      <summary className="cursor-pointer select-none">
        ボットを含む数字です（除外できません）。日次の数字とは比べられません。
        <span className="ml-1 text-ink underline underline-offset-4">詳しく</span>
      </summary>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        <li>
          リアルタイムでは言語で絞り込めないため、ボットを除外できません。日次の数字はボットを除外しているので、そのままは比べられません。
        </li>
        <li>
          主に見るのは PV です。GA4 を Zaraz で入れているサイトでは、UU（アクティブユーザー）が多めに出ることがあります（ページを離れた後に送られるイベントも数えるため。推測）。
        </li>
        <li>国は出しません。Zaraz の影響で、日本の読者の一部が米国と判定されているためです。</li>
        <li>数字は取得した時刻のものです。取り直すと変わります。</li>
      </ul>
    </details>
  );
}
