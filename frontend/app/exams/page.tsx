"use client";

import { AppShell } from "../../components/app-shell";
import { ExamBuilder } from "../../components/exam-builder";

export default function ExamsPage() {
  return <AppShell><ExamBuilder initialView="configure" /></AppShell>;
}
