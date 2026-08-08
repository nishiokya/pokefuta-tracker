// ヘッダーの認証表示をログイン状態に応じて切り替える。
//
// pokefuta.com と共有する Supabase セッションクッキー
// (sb-<ref>-auth-token, Domain=.pokefuta.com) を document.cookie から
// 読むだけで、ネットワークリクエストは一切発生しない
// （「PV に比例して Supabase を読ませない」方針）。
// あくまで表示用の判定で、本当の認証はアプリ側のサーバーが行う。
//
// 対象要素:
//  - <div data-auth-guest>   未ログイン時に出す（ログイン / 新規登録）
//  - <a data-auth-user>      ログイン時に出す（アバター＋表示名 → /profile）
//    <span data-auth-name>   ここに表示名を入れる
//  - <a data-login-link>     未ログイン時に href へ redirect パラメータを付ける
//    （pokefuta.com/login がログイン後にこのページへ戻す）
//
// 以前は「ログインボタンのラベルをスタンプ帳に差し替える」実装だったが、
// 認証状態の表示とナビ項目は別物なので分離した（2026-08-08 の統一方針）。
// スタンプ帳は下タブの項目として常設し、認証ピルは認証だけを表す。
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

  function sessionUser(session) {
    if (!session) return null;
    if (session.user && session.user.id) return session.user;

    var payload = decodeJwtPayload(Array.isArray(session) ? session[0] : session.access_token);
    return payload && payload.sub ? payload : null;
  }

  function currentUser() {
    try {
      var raw = readSessionValue(readCookies());
      if (!raw) return null;
      var json = raw.indexOf('base64-') === 0 ? decodeBase64Url(raw.slice(7)) : raw;
      var session = JSON.parse(json);
      // アクセストークン期限切れでも refresh token があればアプリ側で
      // 更新されるので「ログイン中」として扱う
      return sessionUserId(session) ? sessionUser(session) : null;
    } catch (_) {
      return null;
    }
  }

  function displayName(user) {
    if (!user) return '';
    var meta = user.user_metadata || {};
    if (meta.display_name) return meta.display_name;
    if (user.email) return String(user.email).split('@')[0];
    return 'トレーナー';
  }

  function setHidden(node, hidden) {
    if (!node) return;
    if (hidden) node.setAttribute('hidden', '');
    else node.removeAttribute('hidden');
  }

  function apply() {
    var user = currentUser();
    var links = document.querySelectorAll('[data-login-link]');

    for (var i = 0; i < links.length; i++) {
      var link = links[i];
      if (user) {
        // ログイン中はログイン画面へ送らない。
        // data-stamp-page を持つナビ項目（下タブのスタンプ帳）は本来の遷移先へ差し替える。
        // ラベルは書き換えない（認証状態の表示とナビ項目は別物）。
        var stampPage = link.getAttribute('data-stamp-page');
        if (stampPage) link.href = stampPage;
      } else {
        // 未ログインはログイン後に戻ってこられるよう redirect を積む
        try {
          var url = new URL(link.href);
          url.searchParams.set('redirect', location.href);
          link.href = url.toString();
        } catch (_) {
          /* href が不正でも既定のリンク先のまま動く */
        }
      }
    }

    // 既定は未ログイン表示。ログインしている場合だけ差し替える
    var guest = document.querySelector('[data-auth-guest]');
    var authed = document.querySelector('[data-auth-user]');
    var nameSlot = document.querySelector('[data-auth-name]');
    if (nameSlot) nameSlot.textContent = displayName(user);
    setHidden(guest, Boolean(user));
    setHidden(authed, !user);
  }

  // <details> のサイトスイッチャーは外側クリックでは閉じないので面倒を見る。
  // ここが全ページに載る唯一のスクリプトなので同居させている。
  function closeSwitchOnOutsideClick() {
    document.addEventListener('click', function (event) {
      var open = document.querySelectorAll('details.site-switch[open]');
      for (var i = 0; i < open.length; i++) {
        if (!open[i].contains(event.target)) open[i].removeAttribute('open');
      }
    });
    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape') return;
      var open = document.querySelectorAll('details.site-switch[open]');
      for (var i = 0; i < open.length; i++) open[i].removeAttribute('open');
    });
  }

  function init() {
    apply();
    closeSwitchOnOutsideClick();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
