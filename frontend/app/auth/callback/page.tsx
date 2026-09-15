"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "../../../lib/supabase";

export default function AuthCallbackPage() {
  const router = useRouter();
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("code");
    if (!code) { router.replace("/"); return; }
    supabase.auth.exchangeCodeForSession(code).finally(() => router.replace("/"));
  }, [router]);
  return <main className="auth-page">Completing sign-in…</main>;
}
