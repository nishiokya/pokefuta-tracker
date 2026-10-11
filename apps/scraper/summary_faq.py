"""/summary/（日本語版）の「ポケふた雑学」を、カテゴリつきの FAQ として組み立てる（内部ライブラリ）。

数字の言い換え（「北海道に50枚」など）ではなく、「へえ」となる話を Q&A で並べる。
答えはすべてリポジトリのデータから組み立て、データに無い話は書かない。

- ご当地・語呂合わせ／応援ポケモン … dataset/prefecture_trivia.json（公式の出典つきのものだけ）
- 記録・端っこ … docs/pokefuta.ndjson の titles（north_end など）と pokemons
- 場所 … docs/pokefuta.ndjson の tags（テーマページがあるものはそこへ送る）

質問文だけはここに手で書く（トリビアの id ごと）。トリビアの文が直れば答えも変わり、
id が消えればその質問も出なくなる。日本語のデータしか無いので ja 専用。
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from display_names import compose_display_name

try:
    from apps.scraper.municipalities import build_municipalities, load_slugs, municipality_label
    from apps.scraper.prefectures import PREFECTURE_SLUGS
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from municipalities import build_municipalities, load_slugs, municipality_label
    from prefectures import PREFECTURE_SLUGS

EXCLUDED_POKEMON = "ローカルActs"

# トリビアの id → 質問文。並びがそのまま FAQ の並びになる
TRIVIA_QUESTIONS: dict[str, tuple[str, str]] = {
    # (カテゴリ, 質問)
    "kagoshima-ibusuki-eevee": ("ご当地・語呂合わせ", "指宿市にイーブイの仲間のポケふたが集まっているのはなぜ？"),
    "kagawa-slowpoke-wordplay": ("ご当地・語呂合わせ", "香川県の推しポケモンがヤドンなのはなぜ？"),
    "iwate-geodude-wordplay": ("ご当地・語呂合わせ", "岩手県の応援ポケモンがイシツブテなのはなぜ？"),
    "niigata-ojiya-koi": ("ご当地・語呂合わせ", "小千谷市にコイキングのポケふたがあるのはなぜ？"),
    "tottori-sand": ("ご当地・語呂合わせ", "鳥取県の推しポケモンがサンドなのはなぜ？"),
    "ishikawa-noto-with-you": ("ご当地・語呂合わせ", "能登のポケふたの縁に書かれている言葉は？"),
    "tokyo-pokepark-kanto-admission": ("ご当地・語呂合わせ", "入場しないと見られないポケふたがあるって本当？"),
}

CATEGORY_ORDER = ["ご当地・語呂合わせ", "応援ポケモン", "記録・端っこ", "場所"]
HERO_CATEGORIES = {"ご当地・語呂合わせ", "記録・端っこ"}

ENDS = [("north_end", "いちばん北"), ("south_end", "いちばん南"), ("east_end", "いちばん東"), ("west_end", "いちばん西")]

PLACE_TAGS = [
    ("remote_island", "離島にあるポケふたは何枚？", "離島"),
    ("world_heritage", "世界遺産の近くにあるポケふたは何枚？", "世界遺産の近く"),
    ("roadside", "道の駅やサービスエリアにあるポケふたは何枚？", "道の駅・SA"),
]


@dataclass
class FaqItem:
    id: str
    category: str
    question: str
    answer_html: str  # エスケープ済み
    answer_text: str  # 構造化データ用のプレーンテキスト
    lead: str  # ヒーローに出す一文の答え
    link_href: str = ""
    link_label: str = ""
    sources: list[tuple[str, str]] = field(default_factory=list)


def _manhole_href(record: dict) -> str:
    return f"/manholes/{quote(str(record.get('id', '')), safe='')}/"


def _prefecture_href(pref: str) -> str:
    slug = PREFECTURE_SLUGS.get(pref, "")
    return f"/prefectures/{slug}/" if slug else "/prefectures/"


def _place(record: dict) -> str:
    """「北海道稚内市 キタカラ敷地内」のような場所の書き方（市区町村名は市区町村ページと同じ）。"""
    pref = record.get("prefecture", "")
    city = municipality_label(record)
    name = compose_display_name(record)
    if not name or "/" in name:
        # 施設名の無い蓋は title（「沖縄県/石垣市」）しか無い
        return f"{pref}{city}"
    if name.startswith(city):
        return f"{pref}{name}"
    return f"{pref}{city} {name}"


def _link(href: str, text: str, external: bool = False) -> str:
    extra = ' target="_blank" rel="noopener noreferrer"' if external else ""
    return f'<a class="summary-link" href="{escape(href)}"{extra}>{escape(text)}</a>'


def load_trivia(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _official_trivia(trivia_data: list[dict]) -> dict[str, tuple[str, dict]]:
    """公式の出典があるトリビアだけを {id: (県名, entry)} にする。"""
    out = {}
    for pref in trivia_data:
        for entry in pref.get("trivia", []):
            if entry.get("source_type") == "official" and entry.get("text") and entry.get("id"):
                out[entry["id"]] = (pref.get("prefecture", ""), entry)
    return out


def _trivia_items(official: dict[str, tuple[str, dict]]) -> list[FaqItem]:
    items = []
    for trivia_id, (category, question) in TRIVIA_QUESTIONS.items():
        if trivia_id not in official:
            continue
        pref, entry = official[trivia_id]
        text = entry["text"].rstrip("。")
        source = (entry.get("source_label", "出典"), entry.get("source_url", ""))
        answer_html = (
            f"<p>{escape(text)}。</p>"
            f'<p class="faq-links">{_link(_prefecture_href(pref), f"{pref}のポケふた")}'
            + (f"・出典: {_link(source[1], source[0], external=True)}" if source[1] else "")
            + "</p>"
        )
        items.append(FaqItem(
            id=trivia_id, category=category, question=question,
            answer_html=answer_html, answer_text=f"{text}。", lead=f"{text}。",
            link_href=_prefecture_href(pref), link_label=f"{pref}のポケふたを見る",
            sources=[source] if source[1] else [],
        ))
    return items


def _support_item(official: dict[str, tuple[str, dict]], trivia_data: list[dict]) -> list[FaqItem]:
    support = [
        (pref, entry)
        for p in trivia_data
        for entry in p.get("trivia", [])
        if entry.get("type") == "support_pokemon" and entry.get("id") in official
        for pref in [p.get("prefecture", "")]
    ]
    if not support:
        return []
    rows = "".join(
        f"<li>{_link(_prefecture_href(pref), pref)}: {escape(entry['text'].rstrip('。'))}</li>" for pref, entry in support
    )
    names = "・".join(pref for pref, _ in support)
    lead = f"県ごとに地域を応援するポケモンがいて、{len(support)}つの道県（{names}）でポケふたにも描かれています。"
    return [FaqItem(
        id="support-pokemon", category="応援ポケモン",
        question="都道府県の「応援ポケモン」って？",
        answer_html=(
            f"<p>{escape(lead)}</p><ul>{rows}</ul>"
            f'<p class="faq-links">出典: {_link("https://local.pokemon.jp/", "ポケモンローカルActs", external=True)}</p>'
        ),
        answer_text=lead + " " + " ".join(f"{pref}: {entry['text'].rstrip('。')}。" for pref, entry in support),
        lead=lead,
        link_href="/prefectures/", link_label="都道府県のポケふたを見る",
    )]


def _record_items(records: list[dict], pokemon_slugs: dict[str, str]) -> list[FaqItem]:
    items: list[FaqItem] = []
    by_title: dict[str, list[dict]] = {}
    for record in records:
        for title in record.get("titles", []):
            by_title.setdefault(title.get("key", ""), []).append(record)

    # 東西南北の端
    ends = []  # 同じ蓋が2つの端を兼ねる（石垣市は最南端で最西端）ときは1行にまとめる
    for key, label in ENDS:
        if not by_title.get(key):
            continue
        record = by_title[key][0]
        same = next((i for i, (_, r) in enumerate(ends) if r.get("id") == record.get("id")), None)
        if same is None:
            ends.append((label, record))
        else:
            ends[same] = (f"{ends[same][0]}・{label}", record)
    if ends:
        rows = "".join(
            f"<li>{escape(label)}: {_link(_manhole_href(r), _place(r))}</li>" for label, r in ends
        )
        north = next((r for label, r in ends if label.startswith("いちばん北")), None)
        lead = (
            f"いちばん北のポケふたは{_place(north)}にあります。" if north
            else f"{ends[0][0]}のポケふたは{_place(ends[0][1])}にあります。"
        )
        items.append(FaqItem(
            id="ends", category="記録・端っこ", question="日本の東西南北の端にあるポケふたは？",
            answer_html=f"<ul>{rows}</ul>",
            answer_text=" ".join(f"{label}: {_place(r)}。" for label, r in ends),
            lead=lead,
            link_href=_manhole_href(north or ends[0][1]), link_label="このポケふたを見る",
        ))

    pokemon_counts = Counter(
        name for record in records for name in set(record.get("pokemons", [])) if EXCLUDED_POKEMON not in name
    )
    if pokemon_counts:
        singles = sorted(name for name, n in pokemon_counts.items() if n == 1)
        lead = (
            f"全国のポケふたに描かれた{len(pokemon_counts)}種類のポケモンのうち、"
            f"{len(singles)}種類は全国で1枚にしか描かれていません。"
        )
        items.append(FaqItem(
            id="single-pokemon", category="記録・端っこ", question="全国で1枚にしか描かれていないポケモンは何種類？",
            answer_html=f"<p>{escape(lead)}</p>",
            answer_text=lead, lead=lead,
            link_href="/pokemon/", link_label="ポケモンから探す",
        ))
        top_name, top_count = pokemon_counts.most_common(1)[0]
        lead = f"いちばん多く描かれているポケモンは{top_name}で、{top_count}枚のポケふたに登場します。"
        slug = pokemon_slugs.get(top_name, "")
        href = f"/pokemon/{quote(slug)}/" if slug else "/pokemon/"
        items.append(FaqItem(
            id="top-pokemon", category="記録・端っこ", question="いちばん多くのポケふたに描かれているポケモンは？",
            answer_html=f"<p>{escape(lead)}</p><p class=\"faq-links\">{_link(href, f'{top_name}のポケふた')}</p>",
            answer_text=lead, lead=lead, link_href=href, link_label=f"{top_name}のポケふたを見る",
        ))

    municipalities = build_municipalities(records, load_slugs())
    if municipalities:
        top = municipalities[0].count
        leaders = [f"{m.prefecture}{m.name}" for m in municipalities if m.count == top]
        lead = f"ポケふたがいちばん多い市区町村は{'・'.join(leaders)}で、{top}枚あります。"
        items.append(FaqItem(
            id="top-city", category="記録・端っこ", question="ポケふたがいちばん多い市区町村は？",
            answer_html=f"<p>{escape(lead)}</p><p class=\"faq-links\">{_link('/municipalities/', '市区町村ランキング')}</p>",
            answer_text=lead, lead=lead, link_href="/municipalities/", link_label="市区町村ランキングを見る",
        ))

    lone = by_title.get("lone_100", [])
    if lone:
        label = next(t["label"] for t in lone[0]["titles"] if t.get("key") == "lone_100")
        rows = "".join(f"<li>{_link(_manhole_href(r), _place(r))}</li>" for r in lone)
        lead = f"まわりにほかのポケふたが無い「{label}」は{len(lone)}枚あります。"
        items.append(FaqItem(
            id="lone", category="記録・端っこ", question="近くにほかのポケふたが無い、ぽつんと一枚は？",
            answer_html=f"<p>{escape(lead)}</p><ul>{rows}</ul>",
            answer_text=lead + " " + " ".join(f"{_place(r)}。" for r in lone),
            lead=lead, link_href=_manhole_href(lone[0]), link_label="このポケふたを見る",
        ))
    return items


def _place_items(records: list[dict], tag_page_hrefs: dict[str, str]) -> list[FaqItem]:
    items = []
    for tag, question, label in PLACE_TAGS:
        count = sum(1 for r in records if tag in (r.get("tags") or []))
        if not count:
            continue
        href = tag_page_hrefs.get(tag, "")
        lead = f"{label}にあるポケふたは{count}枚あります。"
        items.append(FaqItem(
            id=f"place-{tag}", category="場所", question=question,
            answer_html=f"<p>{escape(lead)}</p>" + (f'<p class="faq-links">{_link(href, f"{label}のポケふた一覧")}</p>' if href else ""),
            answer_text=lead, lead=lead, link_href=href, link_label=f"{label}のポケふたを見る" if href else "",
        ))
    return items


def build_faq(
    records: list[dict],
    trivia_data: list[dict],
    pokemon_slugs: dict[str, str],
    tag_page_hrefs: dict[str, str],
) -> list[FaqItem]:
    official = _official_trivia(trivia_data)
    items = (
        _trivia_items(official)
        + _support_item(official, trivia_data)
        + _record_items(records, pokemon_slugs)
        + _place_items(records, tag_page_hrefs)
    )
    return sorted(items, key=lambda item: CATEGORY_ORDER.index(item.category))


def todays_item(items: list[FaqItem], today: date) -> FaqItem | None:
    """ヒーローに出す「今日の雑学」。行き先のある項目から日付で順番に選ぶ（毎日のデプロイで変わる）。"""
    # 数の話（場所）は「へえ」となりにくいので、ご当地・語呂合わせと記録の話だけから選ぶ
    candidates = [item for item in items if item.link_href and item.category in HERO_CATEGORIES]
    return candidates[today.toordinal() % len(candidates)] if candidates else None


def render_faq_section(items: list[FaqItem]) -> str:
    if not items:
        return ""
    blocks = []
    for category in CATEGORY_ORDER:
        rows = "".join(
            f'<details class="faq-item" id="faq-{escape(item.id)}">'
            f'<summary data-summary-event="summary_faq_open" data-content-type="faq" '
            f'data-content-id="{escape(item.id)}">{escape(item.question)}</summary>'
            f'<div class="faq-answer">{item.answer_html}</div></details>'
            for item in items if item.category == category
        )
        if rows:
            blocks.append(f'<div class="faq-category"><h3>{escape(category)}</h3>{rows}</div>')
    return (
        '\n    <section class="summary-section" aria-labelledby="fact-list-heading">'
        '\n      <h2 id="fact-list-heading">ポケふた雑学</h2>'
        f'\n      {"".join(blocks)}'
        '\n    </section>\n'
    )


def faq_json_ld(items: list[FaqItem]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item.question,
                "acceptedAnswer": {"@type": "Answer", "text": item.answer_text},
            }
            for item in items
        ],
    }
