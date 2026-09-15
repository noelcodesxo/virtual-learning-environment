import type { Metadata } from "next";
import "./globals.css";
import { AuthGate } from "../components/auth-gate";

export const metadata: Metadata = { title: "Study Assistant", description: "Ask questions and build exams from your indexed library." };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AuthGate>{children}</AuthGate></body></html>;
}
