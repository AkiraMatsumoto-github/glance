import { SitesView } from "@/components/sites/sites-view";

// デモのサイト設定（docs/01_design/screen_design.md §6）。見るだけで、追加・名前・並び・削除はできない。
// 一覧は /api/demo/sites・/api/demo/ga4/properties（ダミーだけを返す。DB・Google・利用者のデータには触れない）から取る
export default function DemoSitesPage() {
  return <SitesView demo />;
}
