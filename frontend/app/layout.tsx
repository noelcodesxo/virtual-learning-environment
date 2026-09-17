import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Study Assistant",
  description: "Ask questions and build exams from your indexed library.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
