"use client";

import type { Session } from "@supabase/supabase-js";
import { useEffect, useState } from "react";
import { isSupabaseConfigured, supabase } from "../lib/supabase";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  useEffect(() => {
    if (!isSupabaseConfigured) { setSession(null); return; }
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => data.subscription.unsubscribe();
  }, []);
  async function signIn() {
    await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: `${window.location.origin}/auth/callback` } });
  }
  if (session === undefined) return <main className="auth-page">Loading…</main>;
  if (!session) return <main className="auth-page"><section><h1>Study Assistant</h1><p>{isSupabaseConfigured ? "Sign in to keep your chats and exams private." : "Supabase authentication has not been configured yet."}</p>{isSupabaseConfigured && <button type="button" onClick={signIn}>Continue with Google</button>}</section></main>;
  return <>{children}</>;
}
