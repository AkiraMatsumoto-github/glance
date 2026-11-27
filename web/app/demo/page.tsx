import { RealtimeView } from "@/components/realtime/realtime-view";

// デモのリアルタイム（docs/01_design/screen_design.md §6）。
// 数字は /api/demo/realtime（ダミーだけを返す。DB・Google・利用者のデータには触れない）から取る
export default function DemoPage() {
  return <RealtimeView endpoint="/api/demo/realtime" />;
}
