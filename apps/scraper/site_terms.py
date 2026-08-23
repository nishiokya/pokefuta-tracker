"""ポケふたを各言語で何と呼ぶかの正（single source of truth）。

**英語は The Pokémon Company の公式表記「Poké Lids」（単数 Poké Lid）を使う。**

以前は呼称の持ち主が決まっておらず、同じ英語ページの中でも表記が割れていた:

- 地図ページ（`apps/web/i18n/strings.en.json`）だけが公式表記の "Poké Lids"
- 集計・都道府県・ポケモンの各ジェネレータは "Pokéfuta"
- 雑学ブロックはアクセント無しの "Pokefuta"

「Pokéfuta」は英語圏でも検索語として使われているので、**タイトル・meta・
ハッシュタグには別名として残し、本文の呼称だけを Poké Lids に統一する**。
消してしまうと既存の検索流入を落とすため。

各ジェネレータの文言そのものはこれまでどおりロケール辞書が持つ。この
モジュールが持つのは「用語表」と「単複のある言語でも壊れない組み立て方」だけ。
"""

from __future__ import annotations

from typing import Mapping

# 本文で使う呼称。単数と複数を分けているのは英語だけで、他は同形。
TERMS: dict[str, dict[str, str]] = {
    "ja": {"one": "ポケふた", "other": "ポケふた"},
    "en": {"one": "Poké Lid", "other": "Poké Lids"},
    "zh-CN": {"one": "宝可梦井盖", "other": "宝可梦井盖"},
    "zh-TW": {"one": "寶可夢人孔蓋", "other": "寶可夢人孔蓋"},
    "ko": {"one": "포켓뚜껑", "other": "포켓뚜껑"},
}

# 検索語として残す別名。本文には使わない。
SEARCH_ALIAS = "Pokéfuta"


def term(lang: str, count: int = 2) -> str:
    """その言語での呼称を返す。count == 1 のときだけ単数形。"""
    forms = TERMS.get(lang, TERMS["en"])
    return forms["one"] if count == 1 else forms["other"]


def format_count(strings: Mapping[str, str], key: str, count: int, **kwargs) -> str:
    """`{count}` を含む文言を、単複のある言語でも正しく組み立てる。

    英語は 1 枚だけのときに "1 Poké Lids" になってしまうので、`<key>_one` を
    定義したロケールでは count == 1 でそちらを使う。日本語・中国語・韓国語は
    `_one` を持たないため、これまでどおり `<key>` がそのまま使われる。
    """
    template = strings.get(f"{key}_one") if count == 1 else None
    if template is None:
        template = strings[key]
    return template.format(count=count, **kwargs)
