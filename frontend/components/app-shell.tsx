import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isExams = pathname.startsWith("/exams");
  const isResources = pathname.startsWith("/resources");
  return (
    <div className="app">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <aside className="app-rail">
        <div className="wordmark">
          <span className="wordmark-text">Virtual Learning Environment</span>
        </div>
        <nav className="app-nav" aria-label="Primary navigation">
          <Link
            className={!isExams && !isResources ? "active" : ""}
            aria-current={!isExams && !isResources ? "page" : undefined}
            href="/"
          >
            Chat
          </Link>
          <Link className={isExams ? "active" : ""} aria-current={isExams ? "page" : undefined} href="/exams">
            Exams
          </Link>
          <Link
            className={isResources ? "active" : ""}
            aria-current={isResources ? "page" : undefined}
            href="/resources"
          >
            Resources
          </Link>
        </nav>
      </aside>
      <main className="main" id="main-content">
        {children}
      </main>
    </div>
  );
}
