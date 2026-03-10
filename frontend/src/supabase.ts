/**
 * Supabase client for Realtime subscriptions.
 * Uses VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY from env.
 */

import { createClient } from '@supabase/supabase-js';

const url = typeof import.meta !== 'undefined' && import.meta.env?.VITE_SUPABASE_URL
  ? String(import.meta.env.VITE_SUPABASE_URL).trim()
  : 'http://127.0.0.1:54321';
const anonKey = typeof import.meta !== 'undefined' && import.meta.env?.VITE_SUPABASE_ANON_KEY
  ? String(import.meta.env.VITE_SUPABASE_ANON_KEY).trim()
  : '';

export const supabase = anonKey && url
  ? createClient(url, anonKey)
  : null;
