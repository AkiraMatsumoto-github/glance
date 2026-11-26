import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Glance",
  description: "GA4・Search Console・Bing のデータを AI と分析する",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ja" className="h-full antialiased">
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
