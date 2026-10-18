"""Shared Japanese prefecture names and URL slugs."""

from __future__ import annotations

PREFECTURES: list[tuple[str, str]] = [
    ("北海道", "hokkaido"), ("青森県", "aomori"), ("岩手県", "iwate"),
    ("宮城県", "miyagi"), ("秋田県", "akita"), ("山形県", "yamagata"),
    ("福島県", "fukushima"), ("茨城県", "ibaraki"), ("栃木県", "tochigi"),
    ("群馬県", "gunma"), ("埼玉県", "saitama"), ("千葉県", "chiba"),
    ("東京都", "tokyo"), ("神奈川県", "kanagawa"), ("新潟県", "niigata"),
    ("富山県", "toyama"), ("石川県", "ishikawa"), ("福井県", "fukui"),
    ("山梨県", "yamanashi"), ("長野県", "nagano"), ("岐阜県", "gifu"),
    ("静岡県", "shizuoka"), ("愛知県", "aichi"), ("三重県", "mie"),
    ("滋賀県", "shiga"), ("京都府", "kyoto"), ("大阪府", "osaka"),
    ("兵庫県", "hyogo"), ("奈良県", "nara"), ("和歌山県", "wakayama"),
    ("鳥取県", "tottori"), ("島根県", "shimane"), ("岡山県", "okayama"),
    ("広島県", "hiroshima"), ("山口県", "yamaguchi"), ("徳島県", "tokushima"),
    ("香川県", "kagawa"), ("愛媛県", "ehime"), ("高知県", "kochi"),
    ("福岡県", "fukuoka"), ("佐賀県", "saga"), ("長崎県", "nagasaki"),
    ("熊本県", "kumamoto"), ("大分県", "oita"), ("宮崎県", "miyazaki"),
    ("鹿児島県", "kagoshima"), ("沖縄県", "okinawa"),
]

PREFECTURE_ORDER = [name for name, _ in PREFECTURES]
PREFECTURE_SLUGS = dict(PREFECTURES)

# 地方の区分。都道府県一覧・トップ・全国一覧（summary）で同じものを使う
# 県ページを訳してある言語（/<lang>/prefectures/。generate_prefecture_pages_i18n.py が作る）。
# 日本語版の hreflang とサイトマップもこれを見る
PREFECTURE_PAGE_LANGS: list[str] = ["en", "zh-TW"]

REGIONS: list[tuple[str, list[str]]] = [
    ("北海道・東北", PREFECTURE_ORDER[0:7]),
    ("関東", PREFECTURE_ORDER[7:14]),
    ("中部", PREFECTURE_ORDER[14:23]),
    ("近畿", PREFECTURE_ORDER[23:30]),
    ("中国", PREFECTURE_ORDER[30:35]),
    ("四国", PREFECTURE_ORDER[35:39]),
    ("九州・沖縄", PREFECTURE_ORDER[39:47]),
]


def select_full_coverage_pokemon(pokemon_coverage: list[dict]) -> dict | None:
    """Pick the pokemon_coverage entry (from dataset/prefecture_trivia.json)
    that appears on every manhole in a prefecture (coverage_percent == 100),
    preferring the entry covering the most Pokemon (a family/group label)
    and, as a tie-break, the entry with the highest cover_count.

    Shared by generate_summary_pages.py's per-prefecture trivia card and
    generate_prefecture_pages.py's /prefectures/ index cards so the two
    pages never disagree on which Pokemon a prefecture's "100% coverage"
    trivia badge names. The winning entry is not guaranteed to have a
    "label" — callers must use `.get("label")` (not `[...]`) and handle a
    missing label themselves, the same way they already handle a `None`
    return.
    """
    full_coverage = [
        entry for entry in pokemon_coverage
        if entry.get("coverage_percent") == 100
    ]
    return max(
        full_coverage,
        key=lambda entry: (len(entry.get("pokemon", [])), entry.get("cover_count", 0)),
        default=None,
    )
