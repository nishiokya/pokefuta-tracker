#!/usr/bin/env python3
"""Inject the shared navigation chrome (header + bottom tabs) into every page.

pokefuta.com（写真館）と同じクロムを図鑑側にも出すための注入スクリプト。
写真館側の実装は `nishiokya/pokefuta` の `src/components/SiteChrome.tsx`、
色・寸法の正は同リポジトリの `src/app/site-chrome-tokens.css`。

構成（2026-08-08 の統一方針にあわせて再構成）:
  - PC (>=1024px): ベージュのバー1本。サイトスイッチャー + ナビ + Info/X + 認証
  - SP (<1024px) : クリームの sticky バー（ロゴ・サイト名・認証の3要素のみ）
                   ＋ 画面下のタブ。Info/X/キャラふた は本文末尾のフッターへ

以前は SP でもヘッダーに5項目を詰め込み、タップ領域を32px・文字11pxまで
潰していた。ヘッダーに要素を足すときは下タブかフッターに逃がせないか先に考えること。
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


STYLESHEET_TEMPLATE = '<link rel="stylesheet" href="{asset_base}assets/site-header.css">'
SESSION_BADGE_SCRIPT_TEMPLATE = '<script src="{asset_base}assets/session-badge.js" defer></script>'

# pokefuta.com への導線には必ず `from=data` を付ける（AGENTS.md）。
# 同一GA4プロパティ内の内部UTMは使わず、着地側の source_app=tracker /
# p_data_referral と突き合わせて分析するため、これが唯一の流入元マーカーになる。
POKEFUTA_APP_URL = "https://pokefuta.com/?from=data"
POKEFUTA_LOGIN_URL = "https://pokefuta.com/login?from=data&mode=login"
# ラベルが「新規登録」なのにログインタブが開かないよう、初期タブを明示する
POKEFUTA_SIGNUP_URL = "https://pokefuta.com/login?from=data&mode=signup"
POKEFUTA_STAMP_URL = "https://pokefuta.com/visits?from=data"
POKEFUTA_PROFILE_URL = "https://pokefuta.com/profile?from=data"
X_ACCOUNT_URL = "https://x.com/pokemonmanhole"

# lucide-react 0.294 系（写真館が使っているもの）と同じ字形を inline SVG で持つ。
# アイコンの言語を両サイトで揃えるため、勝手に別のアイコンへ差し替えないこと。
ICONS = {
    "map": '<polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/>',
    "pokemon": '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
    "summary": '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    # スタンプ帳は写真館の下タブと同じ CircleDot。両サイトで同じ意味に固定する
    "stamp": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="1"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
}


def _icon(name: str) -> str:
    return (
        '<svg class="site-tab__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>'
    )


LABELS = {
    "ja": {
        "nav_aria": "メインナビゲーション",
        "tabs_aria": "サイト内タブ",
        "footer_aria": "サイト内リンク",
        "switch_aria": "サイトを切り替える",
        "brand": "ポケふた",
        "site_dex": "図鑑",
        "site_dex_sub": "調べる・探す",
        "site_album": "写真館",
        "site_album_sub": "撮る・記録する",
        "nav_map": "地図",
        "nav_pokemon": "ポケモン",
        "nav_summary": "集計",
        "nav_character": "キャラふた",
        "tab_stamp": "スタンプ帳",
        "login": "ログイン",
        "signup": "新規登録",
        "profile": "プロフィール",
        "about": "このサイトについて",
        "privacy": "プライバシー",
        "contact": "お問い合わせ",
    },
    "en": {
        "nav_aria": "Main navigation",
        "tabs_aria": "Site tabs",
        "footer_aria": "Site links",
        "switch_aria": "Switch site",
        "brand": "Pokéfuta",
        "site_dex": "Directory",
        "site_dex_sub": "Look up & explore",
        "site_album": "Album",
        "site_album_sub": "Shoot & record",
        "nav_map": "Map",
        "nav_pokemon": "Pokémon",
        "nav_summary": "Stats",
        "nav_character": "Characters",
        "tab_stamp": "Stamps",
        "login": "Login",
        "signup": "Sign up",
        "profile": "Profile",
        "about": "About this site",
        "privacy": "Privacy",
        "contact": "Contact",
    },
    "zh-TW": {
        "nav_aria": "主導覽",
        "tabs_aria": "網站分頁",
        "footer_aria": "站內連結",
        "switch_aria": "切換網站",
        "brand": "寶可夢人孔蓋",
        "site_dex": "圖鑑",
        "site_dex_sub": "查詢與探索",
        "site_album": "相館",
        "site_album_sub": "拍攝與記錄",
        "nav_map": "地圖",
        "nav_pokemon": "神奇寶貝",
        "nav_summary": "統計",
        "nav_character": "角色蓋",
        "tab_stamp": "集章冊",
        "login": "登入",
        "signup": "註冊",
        "profile": "個人檔案",
        "about": "關於本站",
        "privacy": "隱私權",
        "contact": "聯絡我們",
    },
    "zh-CN": {
        "nav_aria": "主导航",
        "tabs_aria": "网站标签",
        "footer_aria": "站内链接",
        "switch_aria": "切换网站",
        "brand": "宝可梦井盖",
        "site_dex": "图鉴",
        "site_dex_sub": "查询与探索",
        "site_album": "相馆",
        "site_album_sub": "拍摄与记录",
        "nav_map": "地图",
        "nav_pokemon": "宝可梦",
        "nav_summary": "统计",
        "nav_character": "角色盖",
        "tab_stamp": "集章册",
        "login": "登录",
        "signup": "注册",
        "profile": "个人资料",
        "about": "关于本站",
        "privacy": "隐私",
        "contact": "联系我们",
    },
    "ko": {
        "nav_aria": "메인 내비게이션",
        "tabs_aria": "사이트 탭",
        "footer_aria": "사이트 링크",
        "switch_aria": "사이트 전환",
        "brand": "포켓뚜껑",
        "site_dex": "도감",
        "site_dex_sub": "찾아보기",
        "site_album": "사진관",
        "site_album_sub": "찍고 기록하기",
        "nav_map": "지도",
        "nav_pokemon": "포켓몬",
        "nav_summary": "통계",
        "nav_character": "캐릭터 맨홀",
        "tab_stamp": "스탬프북",
        "login": "로그인",
        "signup": "가입",
        "profile": "프로필",
        "about": "사이트 소개",
        "privacy": "개인정보처리방침",
        "contact": "문의",
    },
}


HEADER_TEMPLATE = """<header class="site-header">
  <div class="site-header__inner">
    <details class="site-switch">
      <summary class="site-switch__trigger" aria-label="{switch_aria}">
        <span class="site-header__mark" aria-hidden="true"><span class="site-header__mark-core"></span></span>
        <span class="site-header__brand-name">{brand}<span class="site-header__brand-sep" aria-hidden="true">｜</span>{site_dex}</span>
        <span class="site-switch__caret" aria-hidden="true"></span>
      </summary>
      <div class="site-switch__menu">
        <a class="site-switch__item" href="{app_url}"><b>{site_album}</b><small>{site_album_sub}</small></a>
        <a class="site-switch__item is-current" aria-current="true" href="{page_base}"><b>{site_dex}</b><small>{site_dex_sub}</small></a>
        <hr class="site-switch__sep">
        <a class="site-switch__sub" href="{asset_base}character_manholes.html">{nav_character}</a>
        <a class="site-switch__sub" href="{about_url}">{about}</a>
        <a class="site-switch__sub" href="{privacy_url}">{privacy}</a>
        <a class="site-switch__sub" href="{x_url}" target="_blank" rel="noopener noreferrer">X @pokemonmanhole</a>
      </div>
    </details>

    <nav class="site-header__nav" aria-label="{nav_aria}">
      <a class="site-header__link{active_map}" href="{page_base}map.html">{nav_map}</a>
      <a class="site-header__link{active_pokemon}" href="{page_base}pokemon/">{nav_pokemon}</a>
      <a class="site-header__link{active_summary}" href="{page_base}summary/">{nav_summary}</a>
      <a class="site-header__link{active_character}" href="{asset_base}character_manholes.html">{nav_character}</a>
    </nav>

    <a class="site-header__icon" href="{about_url}" title="{about}" aria-label="{about}">{icon_info}</a>
    <a class="site-header__icon site-header__icon--x" href="{x_url}" target="_blank" rel="noopener noreferrer" title="X @pokemonmanhole" aria-label="X @pokemonmanhole">X</a>

    <div class="site-auth" data-auth-guest>
      <a class="site-auth__login" data-login-link href="{login_url}">{login}</a>
      <a class="site-auth__signup" data-login-link href="{signup_url}">{signup}</a>
    </div>
    <a class="site-auth__user" data-auth-user hidden href="{profile_url}" title="{profile}" aria-label="{profile}">
      <span class="site-auth__avatar" aria-hidden="true">👤</span><span class="site-auth__name" data-auth-name></span>
    </a>
  </div>
</header>"""


BOTTOM_TABS_TEMPLATE = """<nav class="site-tabs" aria-label="{tabs_aria}">
  <a class="site-tab{active_map}" href="{page_base}map.html">{icon_map}<span>{nav_map}</span></a>
  <a class="site-tab{active_pokemon}" href="{page_base}pokemon/">{icon_pokemon}<span>{nav_pokemon}</span></a>
  <a class="site-tab{active_summary}" href="{page_base}summary/">{icon_summary}<span>{nav_summary}</span></a>
  <a class="site-tab" data-login-link data-stamp-page="{stamp_url}" href="{login_url}">{icon_stamp}<span>{tab_stamp}</span></a>
</nav>"""


# SP ヘッダーから外した導線の受け皿。
# 全画面地図ページ（map.html / gmanhole_map.html）は本文がビューポート固定で
# フッターに到達できないため、同じ3つをスイッチャーのメニューにも常設している。
# どちらか片方だけ消さないこと。
# ⚠️ <footer> にしないこと。既存ページが <footer role="contentinfo"> を持っており、
# ラベルの無い contentinfo が2つになる。中身はリンク一覧なので nav が正しい。
FOOTER_TEMPLATE = """<nav class="site-footer" aria-label="{footer_aria}">
  <a class="site-footer__link" href="{asset_base}character_manholes.html">{nav_character}</a>
  <a class="site-footer__link" href="{about_url}">{about}</a>
  <a class="site-footer__link" href="{privacy_url}">{privacy}</a>
  <a class="site-footer__link" href="{contact_url}">{contact}</a>
  <a class="site-footer__link" href="{x_url}" target="_blank" rel="noopener noreferrer"><b>X</b> @pokemonmanhole</a>
</nav>"""


LEGACY_HEADER_RE = re.compile(r'<header\s+class="top-app-bar"[^>]*>.*?</header>', flags=re.DOTALL)


def _prefix(target: Path, parent: Path) -> str:
    relative = os.path.relpath(target, parent).replace(os.sep, "/")
    return "./" if relative == "." else f"{relative}/"


def _language(html: str) -> str:
    match = re.search(r'<html\b[^>]*\blang=["\']([^"\']+)', html, re.IGNORECASE)
    return match.group(1) if match and match.group(1) in LABELS else "ja"


def _active_tab(page_path: str | None) -> str | None:
    """現在地のタブを返す。図鑑にはアクティブ表現が一切無かったので追加した。"""
    if not page_path:
        return None
    normalized = page_path.lstrip("./")
    if normalized.startswith("map.html"):
        return "map"
    if normalized.startswith("pokemon/") or normalized == "pokemon":
        return "pokemon"
    if normalized.startswith("summary/") or normalized == "summary":
        return "summary"
    if normalized.startswith("character_manholes.html"):
        return "character"
    return None


def inject(
    html: str,
    asset_base: str = "./",
    page_base: str | None = None,
    page_path: str | None = None,
) -> str:
    """Return HTML with the shared chrome, or unchanged HTML when unsuitable."""
    lower = html.lower()
    if "<body" not in lower or 'http-equiv="refresh"' in lower:
        return html
    if 'class="site-header"' in html:
        return html

    page_base = page_base or asset_base
    labels = LABELS[_language(html)]
    active = _active_tab(page_path)

    fields = dict(labels)
    fields.update(
        asset_base=asset_base,
        page_base=page_base,
        app_url=POKEFUTA_APP_URL,
        login_url=POKEFUTA_LOGIN_URL,
        signup_url=POKEFUTA_SIGNUP_URL,
        stamp_url=POKEFUTA_STAMP_URL,
        profile_url=POKEFUTA_PROFILE_URL,
        about_url=f"{asset_base}about.html",
        privacy_url=f"{asset_base}privacy.html",
        contact_url=f"{asset_base}about.html#contact",
        x_url=X_ACCOUNT_URL,
        icon_info=_icon("info"),
        icon_map=_icon("map"),
        icon_pokemon=_icon("pokemon"),
        icon_summary=_icon("summary"),
        icon_stamp=_icon("stamp"),
        active_map=" is-active" if active == "map" else "",
        active_pokemon=" is-active" if active == "pokemon" else "",
        active_summary=" is-active" if active == "summary" else "",
        active_character=" is-active" if active == "character" else "",
    )

    header = HEADER_TEMPLATE.format(**fields)
    tabs = BOTTOM_TABS_TEMPLATE.format(**fields)
    footer = FOOTER_TEMPLATE.format(**fields)

    stylesheet = STYLESHEET_TEMPLATE.format(asset_base=asset_base)
    if stylesheet not in html:
        html = html.replace("</head>", f"  {stylesheet}\n</head>", 1)

    script = ""
    if "session-badge.js" not in html:
        script = "\n" + SESSION_BADGE_SCRIPT_TEMPLATE.format(asset_base=asset_base)

    body_start = html.lower().find("<body")
    body_end = html.find(">", body_start)
    body_tag = html[body_start : body_end + 1]
    if 'class="' in body_tag:
        new_body_tag = body_tag.replace('class="', 'class="has-site-header ', 1)
    else:
        new_body_tag = body_tag[:-1] + ' class="has-site-header">'
    html = html[:body_start] + new_body_tag + html[body_end + 1 :]

    # フッターと下タブは </body> の直前へ。下タブは position:fixed なので
    # DOM 上の位置は見た目に影響しないが、読み上げ順は本文のあとにする
    trailing = f"\n{footer}\n{tabs}{script}\n"
    body_close = html.lower().rfind("</body>")
    if body_close == -1:
        html = html + trailing
    else:
        html = html[:body_close] + trailing + html[body_close:]

    if LEGACY_HEADER_RE.search(html):
        return LEGACY_HEADER_RE.sub(header, html, count=1)

    insert_at = body_start + len(new_body_tag)
    return html[:insert_at] + "\n" + header + html[insert_at:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default="dist", type=Path)
    args = parser.parse_args()

    updated = 0
    for path in sorted(args.root.rglob("*.html")):
        original = path.read_text(encoding="utf-8")
        language = _language(original)
        localized_root = args.root / language if language != "ja" else args.root
        asset_base = _prefix(args.root, path.parent)
        page_base = _prefix(localized_root, path.parent)
        page_path = os.path.relpath(path, localized_root).replace(os.sep, "/")
        result = inject(original, asset_base=asset_base, page_base=page_base, page_path=page_path)
        if result != original:
            path.write_text(result, encoding="utf-8")
            updated += 1
    print(f"[inject_site_header] updated {updated} HTML files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
