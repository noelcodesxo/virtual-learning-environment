import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const isSupabaseConfigured = Boolean(url && publishableKey);

// A placeholder keeps production builds possible before deployment secrets are injected.
export const supabase = createClient(url ?? "http://localhost", publishableKey ?? "not-configured");
