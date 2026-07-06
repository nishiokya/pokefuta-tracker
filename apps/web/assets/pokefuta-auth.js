// data.pokefuta.com ⇄ pokefuta.com で共有する Supabase セッション。
//
// pokefuta.com アプリと同じ @supabase/ssr のブラウザクライアントを使い、
// 同じクッキー (sb-<ref>-auth-token, Domain=.pokefuta.com) を読み書きする。
// アプリ側の実装: pokefuta リポジトリ src/lib/supabase/cookies.ts
// バージョンはアプリの package.json（@supabase/ssr 0.12）と合わせること。
//
// ここで使う anon key は公開前提のキー（守りは Supabase 側の RLS）。
import { createBrowserClient } from 'https://cdn.jsdelivr.net/npm/@supabase/ssr@0.12/+esm';

const SUPABASE_URL = 'https://kbwzwgsjqvflgfauzcpn.supabase.co';
const SUPABASE_ANON_KEY =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imtid3p3Z3NqcXZmbGdmYXV6Y3BuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTgyODUwMjksImV4cCI6MjA3Mzg2MTAyOX0.6ExSRmih_RQ4GU4cM7p-IPSXXG-9NCgNqOCwH2yFzYQ';

// pokefuta.com 配下では親ドメインクッキーで SSO、
// localhost などでは host-only クッキー（開発・検証用）
const onPokefutaDomain =
  location.hostname === 'pokefuta.com' || location.hostname.endsWith('.pokefuta.com');

export const supabase = createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  cookieOptions: {
    domain: onPokefutaDomain ? '.pokefuta.com' : undefined,
    path: '/',
    sameSite: 'lax',
    secure: location.protocol === 'https:',
  },
});

/** 現在のログインユーザー（未ログインなら null）。サーバー検証付き。 */
export async function getUser() {
  try {
    const { data, error } = await supabase.auth.getUser();
    if (error) return null;
    return data.user ?? null;
  } catch {
    return null;
  }
}

export function signIn(email, password) {
  return supabase.auth.signInWithPassword({ email, password });
}

export function signOut() {
  return supabase.auth.signOut();
}
