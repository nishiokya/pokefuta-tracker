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

  function currentUser() {
    try {
      var raw = readSessionValue(readCookies());
      if (!raw) return null;
      var json = raw.indexOf('base64-') === 0 ? decodeBase64Url(raw.slice(7)) : raw;
      var session = JSON.parse(json);
      // アクセストークン期限切れでも refresh token があればアプリ側で
      // 更新されるので「ログイン中」として扱う
      return session && session.user && session.user.id ? session.user : null;
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
