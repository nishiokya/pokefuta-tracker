// ヘッダーのログインリンクをログイン状態に応じて書き換える。
//
// pokefuta.com と共有する Supabase セッションクッキー
// (sb-<ref>-auth-token, Domain=.pokefuta.com) を document.cookie から
// 読むだけで、ネットワークリクエストは一切発生しない
// （「PV に比例して Supabase を読ませない」方針）。
// あくまで表示用の判定で、本当の認証はアプリ側のサーバーが行う。
//
// 対象要素: <a data-login-link data-stamp-page="..." data-stamp-label="...">
//  - 未ログイン: href に現在ページへの redirect パラメータを付与
//    （pokefuta.com/login がログイン後にこのページへ戻す）
//  - ログイン中: 「スタンプ帳」に差し替え、スタンプ帳へリンク
//
// cookie は data.pokefuta.com 側の @supabase/ssr object 形式と、
// pokefuta.com 側の @supabase/auth-helpers-nextjs array 形式の両方を読む。
(function () {
  'use strict';

  var COOKIE_NAME = 'sb-kbwzwgsjqvflgfauzcpn-auth-token';

  function readCookies() {
    var map = {};
    var parts = document.cookie ? document.cookie.split(';') : [];
    for (var i = 0; i < parts.length; i++) {
      var eq = parts[i].indexOf('=');
      if (eq < 0) continue;
      var name = parts[i].slice(0, eq).trim();
      try {
        map[name] = decodeURIComponent(parts[i].slice(eq + 1).trim());
      } catch (_) {
        map[name] = parts[i].slice(eq + 1).trim();
      }
    }
    return map;
  }

  // @supabase/ssr は約3.2KBを超えるクッキーを name.0, name.1 … に分割する
  function readSessionValue(cookies) {
    if (cookies[COOKIE_NAME]) return cookies[COOKIE_NAME];
    var value = '';
    for (var i = 0; ; i++) {
      var chunk = cookies[COOKIE_NAME + '.' + i];
      if (chunk === undefined) break;
      value += chunk;
    }
    return value || null;
  }

  function decodeBase64Url(payload) {
    var b64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    while (b64.length % 4) b64 += '=';
    // UTF-8 セーフに復元（メールアドレス等は ASCII だが念のため）
    var binary = atob(b64);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new TextDecoder('utf-8').decode(bytes);
  }

  function decodeJwtPayload(token) {
    if (!token || typeof token !== 'string') return null;
    var parts = token.split('.');
    if (parts.length < 2) return null;
    try {
      return JSON.parse(decodeBase64Url(parts[1]));
    } catch (_) {
      return null;
    }
  }

  function sessionUserId(session) {
    if (!session) return null;
    if (session.user && session.user.id) return session.user.id;

    // @supabase/auth-helpers-nextjs stores:
    // [access_token, refresh_token, provider_token, provider_refresh_token, factors]
    if (Array.isArray(session)) {
      var arrayPayload = decodeJwtPayload(session[0]);
      return arrayPayload && arrayPayload.sub ? arrayPayload.sub : null;
    }

    var objectPayload = decodeJwtPayload(session.access_token);
    return objectPayload && objectPayload.sub ? objectPayload.sub : null;
  }

  function currentUser() {
    try {
      var raw = readSessionValue(readCookies());
      if (!raw) return null;
      var json = raw.indexOf('base64-') === 0 ? decodeBase64Url(raw.slice(7)) : raw;
      var session = JSON.parse(json);
      // アクセストークン期限切れでも refresh token があればアプリ側で
      // 更新されるので「ログイン中」として扱う
      return sessionUserId(session) ? session : null;
    } catch (_) {
      return null;
    }
  }

  function apply() {
    var links = document.querySelectorAll('[data-login-link]');
    if (!links.length) return;
    var user = currentUser();
    for (var i = 0; i < links.length; i++) {
      var link = links[i];
      if (user) {
        link.textContent = link.getAttribute('data-stamp-label') || 'スタンプ帳';
        link.setAttribute('data-nav-target', 'stamp');
        var stampPage = link.getAttribute('data-stamp-page');
        if (stampPage) link.href = stampPage;
      } else {
        try {
          var url = new URL(link.href);
          url.searchParams.set('redirect', location.href);
          link.href = url.toString();
        } catch (_) {
          /* href が不正でも既定のリンク先のまま動く */
        }
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply);
  } else {
    apply();
  }
})();
