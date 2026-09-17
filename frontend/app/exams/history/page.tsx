"use client";

import { AppShell } from "../../../components/app-shell";
import { ExamBuilder } from "../../../components/exam-builder";

export default function ExamHistoryPage() {
  return (
    <AppShell>
      <ExamBuilder initialView="history" />
    </AppShell>
  );
}
