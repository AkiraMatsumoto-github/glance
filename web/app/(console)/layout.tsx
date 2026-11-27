import { AppHeader } from "@/components/app-header";

// ログインした後の画面の共通部分（docs/01_design/screen_design.md §1）
export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <AppHeader />
      {/* 幅と余白は、各画面が固定バー（PageBar）と中身（PageBody）で持つ */}
      <main className="flex-1">{children}</main>
    </>
  );
}
