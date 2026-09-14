import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isExams = pathname.startsWith("/exams");
  return <div className="app">
    <a className="skip-link" href="#main-content">Skip to main content</a>
    <aside className="sidebar">
      <div className="wordmark"><span className="mark" aria-hidden="true">▱</span><span className="wordmark-text">Study Assistant</span></div>
      <nav className="mode-switch" aria-label="Study modes">
        <Link className={!isExams ? "active" : ""} href="/">Chat</Link>
        <Link className={isExams ? "active" : ""} href="/exams">Exams</Link>
      </nav>
      <p className="sidebar-note">Ask questions about the indexed library or build a chapter-based exam.</p>
    </aside>
    <main className="main" id="main-content">{children}</main>
  </div>;
}
