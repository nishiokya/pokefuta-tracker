"""蓋ごとの「訪れた人のひとこと」（写真館の visit.comment）を詳細ページ用に整える。

データは import-manhole-photos.yml が書く build/manhole-reviews.json（コミットせず artifact で pages-deploy.yml に渡す。公開訪問のひとことを原文のまま、
訪問ごとに1件）。ここでは次の2つをする。

- 出さないものを落とす: 数字だけの書き込み（自分の訪問の通し番号）と、同じ人が同じ文を
  多くの蓋に書いた定型文。どちらも読む人の役に立たない
- 旅情報チップ: 決まった言い回しを拾って「🅿️ 駐車場あり（口コミ3件・最新 2026-11）」の形にまとめる。
  拾う言い回しは写真館の投稿フォームの候補（pokefuta src/lib/visit-tip.ts の VISIT_TIP_SUGGESTIONS）に
  揃えてあり、候補をタップして書かれた文はそのまま一致する。LLM の要約はしない（書かれていないことを
  足さないため。根拠の件数と日付を必ず添えて、詳しくは原文を読ませる）

落とす・拾う規則をここに置くのは、書き出しをやり直さずに生成だけで直せるようにするため。
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from photo_caption import to_jst_date

logger = logging.getLogger(__name__)

# 詳細ページに原文で出す件数（新しい順）。残りは写真館で読ませる
REVIEWS_SHOWN = 5
# 1件の表示の上限。写真館の入力上限は 500 字だが、実データは最長でも100字台
REVIEW_MAX_CHARS = 200
# 同じ人が同じ文をこの数以上の蓋に書いていたら定型文として出さない
TEMPLATE_MIN_MANHOLES = 3

_NUMBER_ONLY = re.compile(r"[#＃No.．\s]*[0-9０-９]+\s*(枚目|個目|基目|か所目|箇所目|ヶ所目|ヵ所目|つ目)?[\s。.!！]*", re.I)

# (key, 表示, 一致させる言い回し)。並びがチップの並び。
_PARKING_YES = re.compile(
    r"駐車場(が|は|も)?(あり|有り?|ある|あります|完備|無料)|無料駐車場|駐車場に(停|止|とめ)|"
    r"(停|止|とめ)められ|駐車可|停めて|停めた|駐車スペース|コインパーキング"
)
_PARKING_NO = re.compile(
    r"駐車(場|スペース)(は|が)?(なし|無し|ない|無い|ありません|ございません)|駐車できな|(停|止|とめ)められ(ません|ない)|"
    r"(停める|止める|とめる)(所|場所|ところ)(が|は)?(な|無)"
)
TIP_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    # 距離は m（徒歩圏の書き方）だけ。「駅から10km、車で20分」は歩けると言っていない（PR #929 の Codex レビュー）
    ("station", "🚉 駅から歩ける", re.compile(
        r"(?<!道の)駅(から(は|も)?(.{0,4}歩|徒歩|すぐ|近|[0-9０-９〜~]{1,5} ?(m|ｍ|メートル)(?![a-zA-Z]))|前|の(近く|すぐ|目の前|横|隣|前|構内|ロータリー|改札|出口)|構内|すぐ|近く|直結|ロータリー)"
    )),
    # 「道の駅から車で10分」のように、別の場所として出てくる文は数えない（道の駅の名前は空白入り・長いものもある）
    # 「道の駅の向かいの公園」のように道の駅を目印にしているだけの文も数えない（PR #929 の Codex レビュー）
    ("michinoeki", "🏪 道の駅にある", re.compile(
        r"道の駅(?![^。、,，!！?？]{0,15}?(から|まで|へ|方面|経由|向かい|向こう|反対|対岸|隣の|近くの|そばの|裏の|先の))"
    )),
    ("entrance", "🚪 建物の入り口にある", re.compile(r"(入り?口|玄関)(の|に|前|横|付近|近く|脇)")),
    ("eaves", "☂️ ひさしの下にある", re.compile(r"ひさし|庇|屋根の下|屋根付き")),
    ("hard_to_find", "🔍 見つけにくい", re.compile(r"分かりにく|わかりにく|見つけにく|見つからな|迷(っ|い|う)")),
    ("card", "🎴 マンホールカード配布", re.compile(
        r"マンホールカード[^。、,，]{0,16}?(配布(し|中(?!止)|あり|して|され)|配って|もらえ|貰え|ゲット|入手|いただ|頂)"
    )),
]
PARKING_YES_LABEL = "🅿️ 駐車場あり"
PARKING_NO_LABEL = "🅿️ 駐車場なし"

# 一致した直後にこれが来たら打ち消し（「駅前にあるわけではない」）。数える範囲は直後の数文字だけ
# 句読点をまたがない（「駐車場あり。駅から歩けない」の否定は駐車場に掛からない。PR #929 の Copilot レビュー）
_NEGATION_AFTER = re.compile(r"^[^。、,，!！?？]{0,8}?(わけでは|ではな|じゃな|ではありませ|けない|けません|遠|終了|中止|休止|なくな|無くな)")
# すぐ後ろ（句読点をまたがない4文字以内）の否定。「駐車スペースはありません」「停められません」
# （PR #929 の Codex レビュー）。句読点で止めるのは「駐車場あり、トイレはない」を打ち消しにしないため
_NEGATION_NEAR = re.compile(r"^[^。、,，!！?？\s]{0,4}?(ません|ない|無い|なし|無し)")


def _hit(pattern: re.Pattern[str], text: str) -> bool:
    """pattern がどこかで、直後に打ち消しを伴わずに当たるか。"""
    return any(
        not _NEGATION_AFTER.match(rest) and not _NEGATION_NEAR.match(rest)
        for rest in (text[m.end():] for m in pattern.finditer(text))
    )


def normalize_comment(value: object) -> str:
    """空白・改行を1つの空白にまとめる。文字列でなければ空。"""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def is_noise(comment: str) -> bool:
    """数字だけ（訪問の通し番号）や1文字だけの書き込み。"""
    text = comment.strip()
    return len(text) < 2 or bool(_NUMBER_ONLY.fullmatch(text))


def _author_key(review: dict) -> str:
    return str(review.get("public_user_id") or review.get("display_name") or "")


def review_date(review: dict) -> str:
    """並べ替えと表示に使う日付（撮影日 → 投稿日）。ISO 文字列のまま。"""
    return str(review.get("shot_at") or review.get("created_at") or "")


def template_keys(reviews_by_manhole: dict[str, list[dict]]) -> set[tuple[str, str]]:
    """同じ人が同じ文を TEMPLATE_MIN_MANHOLES 以上の蓋に書いた (人, 文) の組。"""
    where: dict[tuple[str, str], set[str]] = defaultdict(set)
    for manhole_id, reviews in reviews_by_manhole.items():
        for review in reviews:
            author = _author_key(review)
            if author:
                where[(author, normalize_comment(review.get("comment")))].add(manhole_id)
    return {key for key, ids in where.items() if len(ids) >= TEMPLATE_MIN_MANHOLES}


def has_tip(comment: str) -> bool:
    """チップのどれかに当たる文か。"""
    return bool(
        _hit(_PARKING_YES, comment) or _hit(_PARKING_NO, comment)
        or any(_hit(pattern, comment) for _, _, pattern in TIP_RULES)
    )


def display_reviews(reviews: list[dict], limit: int = REVIEWS_SHOWN) -> list[dict]:
    """原文で並べる分。同じ蓋に同じ文が何件もあるときは新しい1件だけ出す。

    others は「表示中の投稿者以外で、同じ文を書いた人の数」。同じ人の再訪は数えない。
    公開IDの無い投稿は数えず、表示中の投稿者のIDが分からないときは人数を出さない（0）。
    """
    first: dict[str, dict] = {}
    people: dict[str, set[str]] = defaultdict(set)
    for review in reviews:
        key = review["comment"]
        first.setdefault(key, review)
        if review.get("public_user_id"):
            people[key].add(str(review["public_user_id"]))
    shown = []
    for key, review in first.items():
        own = review.get("public_user_id")
        others = len(people[key] - {str(own)}) if own else 0
        shown.append({**review, "others": others})
    return shown[:limit]


def usable_reviews(reviews_by_manhole: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """出してよいひとことだけを、蓋ごとに新しい順で返す。comment は空白を整えた文に置き換える。"""
    templates = template_keys(reviews_by_manhole)
    out: dict[str, list[dict]] = {}
    for manhole_id, reviews in reviews_by_manhole.items():
        kept = []
        for review in reviews:
            comment = normalize_comment(review.get("comment"))
            if not comment or is_noise(comment):
                continue
            # 定型文でも旅情報を含むもの（投稿フォームの候補をタップした「駅から歩ける」など）は蓋ごとに正しいので残す
            if (_author_key(review), comment) in templates and not has_tip(comment):
                continue
            kept.append({**review, "comment": comment})
        kept.sort(key=review_date, reverse=True)
        if kept:
            out[manhole_id] = kept
    return out


def _jst_month(review: dict) -> str:
    """根拠の年月（YYYY-MM）。本文の日付（format_photo_date）と同じく JST で数える。"""
    day = to_jst_date(review_date(review))
    return day.strftime("%Y-%m") if day else ""


def _chip(key: str, label: str, matched: list[dict]) -> dict[str, Any]:
    return {"key": key, "label": label, "count": len(matched), "latest": _jst_month(matched[0])}


def extract_tips(reviews: list[dict]) -> list[dict[str, Any]]:
    """新しい順のひとことから旅情報チップを作る。各チップは根拠の件数と最新の年月（YYYY-MM）を持つ。

    駐車場は「あり」「なし」が食い違うことがある（廃止など）。いちばん新しい言及の側だけを出す。
    """
    chips: list[dict[str, Any]] = []
    yes = [r for r in reviews if _hit(_PARKING_YES, r["comment"])]
    no = [r for r in reviews if _hit(_PARKING_NO, r["comment"])]
    if yes or no:
        newest_no = review_date(no[0]) if no else ""
        newest_yes = review_date(yes[0]) if yes else ""
        if no and newest_no >= newest_yes:
            chips.append(_chip("parking_no", PARKING_NO_LABEL, no))
        else:
            chips.append(_chip("parking_yes", PARKING_YES_LABEL, yes))
    for key, label, pattern in TIP_RULES:
        matched = [r for r in reviews if _hit(pattern, r["comment"])]
        if matched:
            chips.append(_chip(key, label, matched))
    return chips


def missing_tip_prompt(chips: list[dict[str, Any]]) -> Optional[str]:
    """まだ口コミに無い、旅で一番聞かれる情報。投稿の呼びかけに使う。

    駐車場だけを名指しする。駅からの行き方は車でしか行けない蓋も多く、名指しすると的外れになる。
    """
    keys = {chip["key"] for chip in chips}
    if keys & {"parking_yes", "parking_no"}:
        return None
    return "駐車場の情報がまだありません"


def load_reviews(path: Path) -> Optional[dict[str, list[dict]]]:
    """build/manhole-reviews.json（artifact から pages-deploy.yml が置く）を読み、出してよいものだけを蓋ID（正規化済みの文字列）ごとに返す。

    ファイルが無い・壊れているときは None（ページは口コミの欄なしで出る。日次の生成を止めない）。
    読めたが出せる口コミが0件のときは空の dict（どの蓋も「0件」として呼びかけを出す）。
    この2つを分けるのは、0件の日まで「読めなかった」扱いにして呼びかけを消さないため（PR #929 の Codex レビュー）。
    """
    if not path.exists():
        logger.warning("Reviews file not found: %s", path)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read reviews %s: %s", path, exc)
        return None
    raw = data.get("reviews") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        logger.warning("Reviews file has no reviews object: %s", path)
        return None
    cleaned = {
        str(manhole_id).strip().lstrip("0") or "0": [r for r in reviews if isinstance(r, dict)]
        for manhole_id, reviews in raw.items()
        if isinstance(reviews, list)
    }
    usable = usable_reviews(cleaned)
    logger.info("Loaded reviews for %d manholes (%d shown-eligible)", len(cleaned), sum(map(len, usable.values())))
    return usable
