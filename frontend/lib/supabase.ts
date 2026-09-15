import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const isSupabaseConfigured = Boolean(url && anonKey);

// A placeholder keeps production builds possible before deployment secrets are injected.
export const supabase = createClient(url ?? "http://localhost", anonKey ?? "not-configured");
