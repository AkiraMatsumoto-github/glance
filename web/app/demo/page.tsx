import { RealtimeView } from "@/components/realtime/realtime-view";

// デモのリアルタイム（docs/01_design/screen_design.md §6）。
// 数字は /api/demo/realtime（ダミーだけを返す。DB・Google・利用者のデータには触れない）から取る
export default function DemoPage() {
  return (
    <RealtimeView
      endpoint="/api/demo/realtime"
      intro={
        <p className="rounded-xl border bg-surface px-4 py-3 text-ink-2">
          デモ用のダミーの数字です（サイトも架空です）。ログインすると、あなたの GA4 の数字が出ます。
        </p>
      }
    />
  );
}
