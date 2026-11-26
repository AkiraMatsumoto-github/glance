import { RealtimeView } from "@/components/realtime/realtime-view";

// リアルタイム（docs/01_design/screen_design.md §3）。ログインした人の GA4 の数字
export default function RealtimePage() {
  return <RealtimeView endpoint="/api/realtime" />;
}
