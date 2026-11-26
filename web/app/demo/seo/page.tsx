import { SeoView } from "@/components/seo/seo-view";

// デモの SEO（docs/01_design/screen_design.md §6・§7）。
// 数字は /api/demo/seo（ダミーだけを返す。DB・Google・Bing・利用者のデータには触れない）から取る。
// ログインした後の SEO の画面は、2番目の段階で GSC・Bing の取り込みと一緒に作る
export default function DemoSeoPage() {
  return <SeoView endpoint="/api/demo/seo" />;
}
