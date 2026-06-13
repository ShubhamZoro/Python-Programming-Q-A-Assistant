/**
 * Supabase JS client singleton for the frontend.
 * Used exclusively for auth operations (sign up, sign in, OAuth, session refresh).
 * All data reads/writes go through the backend API with the user's JWT.
 */

import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || "";

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  console.warn(
    "[supabaseClient] VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY is not set. " +
      "Add them to frontend/.env"
  );
}

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    persistSession: true,       // stores session in localStorage automatically
    autoRefreshToken: true,     // silently refreshes the JWT before expiry
    detectSessionInUrl: true,   // parses #access_token=… from OAuth redirect hash
    // flowType: "pkce"         // ← enable once VITE_SUPABASE_ANON_KEY is the real
                                //   anon key from Supabase Dashboard → Settings → API.
                                //   PKCE requires a valid anon key for the code exchange;
                                //   the current placeholder key only supports implicit flow.
  },
});

