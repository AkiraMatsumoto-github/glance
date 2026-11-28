import { SeoView } from "@/components/seo/seo-view";

// SEO（docs/01_design/screen_design.md §7）。取り込んだ Search Console・Bing の数字（/api/seo）
export default function SeoPage() {
  return <SeoView endpoint="/api/seo" />;
}
