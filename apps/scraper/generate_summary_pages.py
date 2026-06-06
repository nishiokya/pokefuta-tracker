#!/usr/bin/env python3
"""Generate static, multilingual summary pages from pokefuta.ndjson.

Outputs:
  dist/summary/index.html          (Japanese)
  dist/en/summary/index.html       (English)
  dist/zh-CN/summary/index.html    (Simplified Chinese)
  dist/zh-TW/summary/index.html    (Traditional Chinese)
  dist/ko/summary/index.html       (Korean)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

ROOT = Path(__file__).parent.parent.parent
NDJSON = ROOT / "docs" / "pokefuta.ndjson"
PREFECTURES_JSON = ROOT / "apps" / "web" / "i18n" / "prefectures.json"
DIST = ROOT / "dist"
POKEMON_METADATA_JSON = ROOT / "docs" / "pokemon_metadata.json"
PHOTOS_JSON = ROOT / "docs" / "latest-manhole-photos.json"
IMAGE_DIR = ROOT / "dataset" / "manhole" / "image"

BASE_URL = "https://data.pokefuta.com"
OGP_IMAGE = f"{BASE_URL}/assets/ogp/pokefuta_summary_ogp.png"

PREFECTURE_ORDER: list[str] = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県",
    "山形県", "福島県", "茨城県", "栃木県", "群馬県",
    "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県",
    "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県",
    "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県",
    "鹿児島県", "沖縄県",
]

REGION_MAP: dict[str, str] = {
    "北海道": "北海道",
    "青森県": "東北", "岩手県": "東北", "宮城県": "東北",
    "秋田県": "東北", "山形県": "東北", "福島県": "東北",
    "茨城県": "関東", "栃木県": "関東", "群馬県": "関東",
    "埼玉県": "関東", "千葉県": "関東", "東京都": "関東", "神奈川県": "関東",
    "新潟県": "中部", "富山県": "中部", "石川県": "中部", "福井県": "中部",
    "山梨県": "中部", "長野県": "中部", "岐阜県": "中部",
    "静岡県": "中部", "愛知県": "中部",
    "三重県": "近畿", "滋賀県": "近畿", "京都府": "近畿",
    "大阪府": "近畿", "兵庫県": "近畿", "奈良県": "近畿", "和歌山県": "近畿",
    "鳥取県": "中国", "島根県": "中国", "岡山県": "中国",
    "広島県": "中国", "山口県": "中国",
    "徳島県": "四国", "香川県": "四国", "愛媛県": "四国", "高知県": "四国",
    "福岡県": "九州", "佐賀県": "九州", "長崎県": "九州",
    "熊本県": "九州", "大分県": "九州", "宮崎県": "九州",
    "鹿児島県": "九州", "沖縄県": "九州",
}

SUMMARY_STRINGS: dict[str, dict] = {
    "ja": {
        "html_lang": "ja",
        "og_locale": "ja_JP",
        "pref_key": "ja",
        "out_path": "summary/index.html",
        "canonical": f"{BASE_URL}/summary",
        "map_base_href": "/",
        "page_title": "全国のポケモンマンホール（ポケふた）一覧・分布マップ",
        "meta_desc": "全国{total}枚のポケモンマンホール「ポケふた」を都道府県別・ポケモン別に検索。旅行先のポケふた探しにご活用ください。",
        "breadcrumb_aria": "パンくず",
        "nav_home_text": "全国マップ",
        "nav_home_href": "/",
        "h1": "全国のポケモンマンホール（ポケふた）一覧",
        "subtitle": "全国{total}枚のポケモンマンホール（ポケふた）を都道府県別・ポケモン別に探せます。旅行先やお出かけ先のポケふた探しにご活用ください。",
        "stats_aria": "全国集計",
        "stat_total": "全国の総数",
        "stat_installed": "設置済み都道府県",
        "stat_empty": "未設置県",
        "total_fmt": "{count}枚",
        "installed_fmt": "{count}都道府県",
        "empty_fmt": "{count}県",
        "h2_pref_count": "都道府県別の設置数一覧",
        "th_pref": "都道府県",
        "th_count": "ポケふた数",
        "th_map": "地図",
        "map_link_text": "地図で見る",
        "table_no_map": "-",
        "count_unit": "枚",
        "h2_ranking": "ポケふたの多い都道府県ランキング",
        "ranking_note": '各都道府県の地図は、<a class="summary-link" href="/">全国マップ</a>から地域を選んで確認できます。',
        "h2_regional": "地域の分布傾向",
        "h2_empty": "ポケふたがない県",
        "empty_note": 'まだポケふたが設置されていない県もあります。今後新しい地域へ広がる可能性があり、"次はどこに設置されるか"を予想する楽しみもあります。',
        "no_empty": "現在、未設置県はありません。",
        "h2_map": "全国マップで探す",
        "map_desc": "設置場所や近くのポケふたは、地図上で確認できます。都道府県フィルターで絞り込んで巡るルートを考えてみましょう。",
        "cta_text": "地図で全国のポケふたを探す →",
        "ai_intro": "全国には{total}枚のポケふたが設置されています。",
        "ai_top": "最も多いのは{top1pref}（{top1count}枚）で、{top3}などに多く分布しています。",
        "ai_empty": "まだ{empty_count}県では設置されていませんが、今後の広がりも期待されます。",
        "ai_outro": "ポケふたは地方観光や地域振興との結びつきが強く、旅行しながら巡る楽しみ方が特徴です。",
        "disc_top_pct": "{pref}だけで全国{pct}%",
        "disc_installed": "ポケふた設置済み",
        "disc_avg": "設置済み県の平均枚数",
        "disc_empty": "まだ未設置の県がある",
        "region_names": {
            "北海道": "北海道", "東北": "東北", "関東": "関東",
            "中部": "中部", "近畿": "近畿", "中国": "中国",
            "四国": "四国", "九州": "九州",
        },
        "discovery_aria": "発見",
        "daily_fact_heading": "今日のポケふた雑学",
        "fact_section_heading": "ポケふた雑学",
        "share_x_text": "Xで共有",
        "view_map_text": "地図で見る",
        "regional_top2": "地方別では{r1name}（{r1count}枚）が最も多く、次いで{r2name}（{r2count}枚）となっています。",
        "regional_top1": "地方別では{r1name}（{r1count}枚）が最も多くなっています。",
        "regional_outro": "ポケふたは地方自治体・観光協会との連携で設置されることが多く、観光地や駅周辺に置かれているケースが目立ちます。地域を旅しながら複数のポケふたを巡るルートを作るのも人気の楽しみ方です。",
        "search_hub": {
            "h2": "ポケふたを探す",
            "card_pref_title": "都道府県から探す",
            "card_pref_desc": "47都道府県の設置数一覧",
            "card_pokemon_title": "ポケモンから探す",
            "card_pokemon_desc": "ポケモン別の一覧ページ",
            "card_map_title": "地図で探す",
            "card_map_desc": "インタラクティブマップで確認",
        },
        "popular_pokemon": {
            "h2": "人気ポケモンのポケふた",
        },
        "latest_photos": {
            "h2": "最新追加写真",
            "note": "ユーザーが投稿した最新のポケふた写真です。タップするとポケふた詳細ページへ移動します。",
        },
        "no_photos": {
            "h2": "まだ写真が投稿されていないポケふた",
            "total": "{count}枚のポケふたに写真がまだありません",
            "cta": "あなたが最初の投稿者になれます。",
        },
        "pokemon_ranking": {
            "h2": "ポケモンランキング",
            "h3_count": "ポケふた数ランキング",
            "h3_pref": "登場自治体数ランキング",
            "pref_count_unit": "自治体",
        },
    },
    "en": {
        "html_lang": "en",
        "og_locale": "en_US",
        "pref_key": "en",
        "out_path": "en/summary/index.html",
        "canonical": f"{BASE_URL}/en/summary",
        "map_base_href": "/en/",
        "page_title": "How Many Pokéfuta Exist Nationwide? Count & Rankings by Prefecture",
        "meta_desc": "Explore the total number of Pokémon manholes (Pokéfuta) nationwide, the count by prefecture, top-ranking prefectures, and prefectures with none installed.",
        "breadcrumb_aria": "Breadcrumb",
        "nav_home_text": "Japan Map",
        "nav_home_href": "/en/",
        "h1": "How Many Pokéfuta Are There Nationwide?",
        "subtitle": "Pokéfuta (Pokémon manhole covers) counted and sorted by prefecture from the latest dataset.",
        "stats_aria": "Nationwide Statistics",
        "stat_total": "Total Nationwide",
        "stat_installed": "Prefectures with Pokéfuta",
        "stat_empty": "Prefectures with None",
        "total_fmt": "{count} Pokéfuta",
        "installed_fmt": "{count} Prefectures",
        "empty_fmt": "{count} Prefectures",
        "h2_pref_count": "Count by Prefecture",
        "th_pref": "Prefecture",
        "th_count": "Pokéfuta",
        "th_map": "Map",
        "map_link_text": "View map",
        "table_no_map": "—",
        "count_unit": "",
        "h2_ranking": "Top Prefectures by Pokéfuta Count",
        "ranking_note": 'Browse each prefecture\'s Pokéfuta on the <a class="summary-link" href="/en/">Japan Map</a>.',
        "h2_regional": "Regional Distribution",
        "h2_empty": "Prefectures with No Pokéfuta",
        "empty_note": 'Some prefectures don\'t have any Pokéfuta yet. Future expansions are possible, and guessing "where will the next one appear?" is part of the fun.',
        "no_empty": "All prefectures currently have at least one Pokéfuta.",
        "h2_map": "Explore on the Map",
        "map_desc": "Find Pokéfuta locations and nearby manholes on the interactive map. Use the prefecture filter to plan your route.",
        "cta_text": "Explore all Pokéfuta on the map →",
        "ai_intro": "There are {total} Pokéfuta installed nationwide.",
        "ai_top": "The most are in {top1pref} ({top1count}), followed by {top3} and others.",
        "ai_empty": "{empty_count} prefectures have no installations yet, but future expansion is expected.",
        "ai_outro": "Pokéfuta are deeply tied to regional tourism and local promotion, making travelling to collect them a beloved activity.",
        "disc_top_pct": "{pref} accounts for {pct}% nationwide",
        "disc_installed": "prefectures with Pokéfuta",
        "disc_avg": "average per installed prefecture",
        "disc_empty": "prefectures still without Pokéfuta",
        "region_names": {
            "北海道": "Hokkaido", "東北": "Tohoku", "関東": "Kanto",
            "中部": "Chubu", "近畿": "Kinki", "中国": "Chugoku",
            "四国": "Shikoku", "九州": "Kyushu",
        },
        "discovery_aria": "Discovery",
        "regional_top2": "By region, {r1name} leads with {r1count} Pokéfuta, followed by {r2name} ({r2count}).",
        "regional_top1": "By region, {r1name} has the most with {r1count} Pokéfuta.",
        "regional_outro": "Pokéfuta are often installed through partnerships with local governments and tourism associations, frequently found near tourist spots and train stations. Planning a multi-region route is a popular way to enjoy them.",
        "search_hub": {
            "h2": "Find Pokéfuta",
            "card_pref_title": "By Prefecture",
            "card_pref_desc": "Count list for all 47 prefectures",
            "card_pokemon_title": "By Pokémon",
            "card_pokemon_desc": "Browse by Pokémon species",
            "card_map_title": "On the Map",
            "card_map_desc": "Interactive map view",
        },
        "popular_pokemon": {
            "h2": "Popular Pokémon on Pokéfuta",
        },
        "pokemon_ranking": {
            "h2": "Pokémon Rankings",
            "h3_count": "By Pokéfuta Count",
            "h3_pref": "By Municipalities",
            "pref_count_unit": " municipalities",
        },
    },
    "zh-CN": {
        "html_lang": "zh-CN",
        "og_locale": "zh_CN",
        "pref_key": "zh-Hans",
        "out_path": "zh-CN/summary/index.html",
        "canonical": f"{BASE_URL}/zh-CN/summary",
        "map_base_href": "/zh-CN/",
        "page_title": "全国共有多少个宝可梦井盖？分都道府县数量与排行榜",
        "meta_desc": "整理了全国宝可梦井盖（Pokéfuta）的总数、各都道府县的设置数量、数量最多的县以及尚未设置的县。",
        "breadcrumb_aria": "面包屑导航",
        "nav_home_text": "全国地图",
        "nav_home_href": "/zh-CN/",
        "h1": "全国共有多少个宝可梦井盖？",
        "subtitle": "基于现有数据，按都道府县统计了全国的宝可梦井盖（宝可梦人孔盖）数量。",
        "stats_aria": "全国统计",
        "stat_total": "全国总数",
        "stat_installed": "已设置都道府县",
        "stat_empty": "未设置县",
        "total_fmt": "{count}个",
        "installed_fmt": "{count}个都道府县",
        "empty_fmt": "{count}县",
        "h2_pref_count": "各都道府县设置数量",
        "th_pref": "都道府县",
        "th_count": "宝可梦井盖数",
        "th_map": "地图",
        "map_link_text": "查看地图",
        "table_no_map": "—",
        "count_unit": "个",
        "h2_ranking": "宝可梦井盖最多的县排名",
        "ranking_note": '各都道府县的地图可通过<a class="summary-link" href="/zh-CN/">全国地图</a>选择地区查看。',
        "h2_regional": "地区分布情况",
        "h2_empty": "没有宝可梦井盖的县",
        "empty_note": '目前仍有部分县未设置宝可梦井盖，未来可能会扩展到新地区，猜测"下一个会设置在哪里"也是一种乐趣。',
        "no_empty": "目前所有都道府县均已设置宝可梦井盖。",
        "h2_map": "在地图上探索",
        "map_desc": "可在地图上确认设置地点及附近的宝可梦井盖。使用都道府县筛选功能制定巡游路线吧。",
        "cta_text": "在地图上查找全国宝可梦井盖 →",
        "ai_intro": "全国共设置了{total}个宝可梦井盖。",
        "ai_top": "最多的是{top1pref}（{top1count}个），{top3}等地分布较为集中。",
        "ai_empty": "目前仍有{empty_count}个县未设置，期待未来进一步扩展。",
        "ai_outro": "宝可梦井盖与地方观光和地区振兴紧密相连，一边旅行一边巡游是其独特魅力。",
        "disc_top_pct": "{pref}占全国{pct}%",
        "disc_installed": "已设置宝可梦井盖",
        "disc_avg": "已设置县的平均数量",
        "disc_empty": "仍未设置的县",
        "region_names": {
            "北海道": "北海道", "東北": "东北", "関東": "关东",
            "中部": "中部", "近畿": "近畿", "中国": "中国",
            "四国": "四国", "九州": "九州",
        },
        "discovery_aria": "发现",
        "regional_top2": "按地区统计，{r1name}（{r1count}个）最多，其次是{r2name}（{r2count}个）。",
        "regional_top1": "按地区统计，{r1name}（{r1count}个）最多。",
        "regional_outro": "宝可梦井盖多通过地方政府和观光协会合作设置，常见于旅游胜地和车站周边。边旅行边规划多地巡游路线也是广受欢迎的玩法。",
        "search_hub": {
            "h2": "寻找宝可梦井盖",
            "card_pref_title": "按都道府县搜索",
            "card_pref_desc": "47个都道府县设置数量一览",
            "card_pokemon_title": "按宝可梦搜索",
            "card_pokemon_desc": "按宝可梦种类浏览",
            "card_map_title": "在地图上搜索",
            "card_map_desc": "互动地图查看",
        },
        "popular_pokemon": {
            "h2": "热门宝可梦井盖",
        },
        "pokemon_ranking": {
            "h2": "宝可梦排行榜",
            "h3_count": "按井盖数量排名",
            "h3_pref": "按出现市区町村数排名",
            "pref_count_unit": "个市区町村",
        },
    },
    "zh-TW": {
        "html_lang": "zh-TW",
        "og_locale": "zh_TW",
        "pref_key": "zh-Hant",
        "out_path": "zh-TW/summary/index.html",
        "canonical": f"{BASE_URL}/zh-TW/summary",
        "map_base_href": "/zh-TW/",
        "page_title": "全國共有多少個寶可夢人孔蓋？各都道府縣數量與排行榜",
        "meta_desc": "整理了全國寶可夢人孔蓋（Pokéfuta）的總數、各都道府縣的設置數量、數量最多的縣以及尚未設置的縣。",
        "breadcrumb_aria": "麵包屑導覽",
        "nav_home_text": "全國地圖",
        "nav_home_href": "/zh-TW/",
        "h1": "全國共有多少個寶可夢人孔蓋？",
        "subtitle": "基於現有資料，按都道府縣統計了全國的寶可夢人孔蓋數量。",
        "stats_aria": "全國統計",
        "stat_total": "全國總數",
        "stat_installed": "已設置都道府縣",
        "stat_empty": "未設置縣",
        "total_fmt": "{count}個",
        "installed_fmt": "{count}個都道府縣",
        "empty_fmt": "{count}縣",
        "h2_pref_count": "各都道府縣設置數量",
        "th_pref": "都道府縣",
        "th_count": "寶可夢人孔蓋數",
        "th_map": "地圖",
        "map_link_text": "查看地圖",
        "table_no_map": "—",
        "count_unit": "個",
        "h2_ranking": "寶可夢人孔蓋最多的縣排行",
        "ranking_note": '各都道府縣的地圖可透過<a class="summary-link" href="/zh-TW/">全國地圖</a>選擇地區查看。',
        "h2_regional": "地區分布情況",
        "h2_empty": "沒有寶可夢人孔蓋的縣",
        "empty_note": "目前仍有部分縣未設置寶可夢人孔蓋，未來可能會擴展到新地區，猜測「下一個會設置在哪裡」也是一種樂趣。",
        "no_empty": "目前所有都道府縣均已設置寶可夢人孔蓋。",
        "h2_map": "在地圖上探索",
        "map_desc": "可在地圖上確認設置地點及附近的寶可夢人孔蓋。使用都道府縣篩選功能規劃巡遊路線吧。",
        "cta_text": "在地圖上查找全國寶可夢人孔蓋 →",
        "ai_intro": "全國共設置了{total}個寶可夢人孔蓋。",
        "ai_top": "最多的是{top1pref}（{top1count}個），{top3}等地分布較為集中。",
        "ai_empty": "目前仍有{empty_count}個縣未設置，期待未來進一步擴展。",
        "ai_outro": "寶可夢人孔蓋與地方觀光和地區振興緊密相連，一邊旅行一邊巡遊是其獨特魅力。",
        "disc_top_pct": "{pref}占全國{pct}%",
        "disc_installed": "已設置寶可夢人孔蓋",
        "disc_avg": "已設置縣的平均數量",
        "disc_empty": "仍未設置的縣",
        "region_names": {
            "北海道": "北海道", "東北": "東北", "関東": "關東",
            "中部": "中部", "近畿": "近畿", "中国": "中國",
            "四国": "四國", "九州": "九州",
        },
        "discovery_aria": "發現",
        "regional_top2": "按地區統計，{r1name}（{r1count}個）最多，其次是{r2name}（{r2count}個）。",
        "regional_top1": "按地區統計，{r1name}（{r1count}個）最多。",
        "regional_outro": "寶可夢人孔蓋多透過地方政府和觀光協會合作設置，常見於旅遊勝地和車站周邊。邊旅行邊規劃多地巡遊路線也是廣受歡迎的玩法。",
        "search_hub": {
            "h2": "尋找寶可夢人孔蓋",
            "card_pref_title": "按都道府縣搜尋",
            "card_pref_desc": "47個都道府縣設置數量一覽",
            "card_pokemon_title": "按寶可夢搜尋",
            "card_pokemon_desc": "按寶可夢種類瀏覽",
            "card_map_title": "在地圖上搜尋",
            "card_map_desc": "互動地圖查看",
        },
        "popular_pokemon": {
            "h2": "熱門寶可夢人孔蓋",
        },
        "pokemon_ranking": {
            "h2": "寶可夢排行榜",
            "h3_count": "按人孔蓋數量排名",
            "h3_pref": "按出現市區町村數排名",
            "pref_count_unit": "個市區町村",
        },
    },
    "ko": {
        "html_lang": "ko",
        "og_locale": "ko_KR",
        "pref_key": "ko",
        "out_path": "ko/summary/index.html",
        "canonical": f"{BASE_URL}/ko/summary",
        "map_base_href": "/ko/",
        "page_title": "포케후타는 전국에 몇 개 있을까? 도도부현별 수량 및 랭킹",
        "meta_desc": "전국 포케후타(포켓몬 맨홀)의 총 수량, 도도부현별 설치 수, 가장 많은 현, 아직 설치되지 않은 현을 정리했습니다.",
        "breadcrumb_aria": "탐색경로",
        "nav_home_text": "전국 지도",
        "nav_home_href": "/ko/",
        "h1": "포케후타는 전국에 몇 개 있을까?",
        "subtitle": "기존 데이터를 바탕으로 전국의 포케후타(포켓몬 맨홀)를 도도부현별로 집계했습니다.",
        "stats_aria": "전국 집계",
        "stat_total": "전국 총 수량",
        "stat_installed": "설치된 도도부현",
        "stat_empty": "미설치 현",
        "total_fmt": "{count}개",
        "installed_fmt": "{count}개 도도부현",
        "empty_fmt": "{count}개 현",
        "h2_pref_count": "도도부현별 설치 수량",
        "th_pref": "도도부현",
        "th_count": "포케후타 수",
        "th_map": "지도",
        "map_link_text": "지도에서 보기",
        "table_no_map": "—",
        "count_unit": "개",
        "h2_ranking": "포케후타가 많은 현 랭킹",
        "ranking_note": '각 도도부현의 지도는 <a class="summary-link" href="/ko/">전국 지도</a>에서 지역을 선택하여 확인할 수 있습니다.',
        "h2_regional": "지역별 분포 현황",
        "h2_empty": "포케후타가 없는 현",
        "empty_note": '아직 포케후타가 설치되지 않은 현도 있습니다. 앞으로 새로운 지역으로 확장될 가능성이 있으며, "다음에는 어디에 설치될까?"를 예상하는 재미도 있습니다.',
        "no_empty": "현재 미설치 현은 없습니다.",
        "h2_map": "전국 지도에서 찾기",
        "map_desc": "설치 장소나 근처 포케후타는 지도에서 확인할 수 있습니다. 도도부현 필터로 좁혀서 순회 경로를 생각해보세요.",
        "cta_text": "지도에서 전국 포케후타 찾기 →",
        "ai_intro": "전국에는 {total}개의 포케후타가 설치되어 있습니다.",
        "ai_top": "가장 많은 곳은 {top1pref}（{top1count}개）이며, {top3} 등에 많이 분포되어 있습니다.",
        "ai_empty": "아직 {empty_count}개 현에는 설치되어 있지 않지만, 앞으로의 확장도 기대됩니다.",
        "ai_outro": "포케후타는 지방 관광 및 지역 진흥과 밀접하게 연결되어 있으며, 여행하면서 수집하는 즐거움이 특징입니다.",
        "disc_top_pct": "{pref}만으로 전국의 {pct}%",
        "disc_installed": "포케후타 설치 완료",
        "disc_avg": "설치 현의 평균 수량",
        "disc_empty": "아직 미설치인 현이 있음",
        "region_names": {
            "北海道": "홋카이도", "東北": "도호쿠", "関東": "간토",
            "中部": "주부", "近畿": "긴키", "中国": "주고쿠",
            "四国": "시코쿠", "九州": "규슈",
        },
        "discovery_aria": "발견",
        "regional_top2": "지역별로는 {r1name}（{r1count}개）이 가장 많으며, 다음은 {r2name}（{r2count}개）입니다.",
        "regional_top1": "지역별로는 {r1name}（{r1count}개）이 가장 많습니다.",
        "regional_outro": "포케후타는 지방자치단체・관광협회와의 협력으로 설치되는 경우가 많으며, 관광지나 역 주변에 위치한 경우가 눈에 띕니다. 지역을 여행하면서 여러 포케후타를 순회하는 경로를 만드는 것도 인기 있는 즐기는 방법입니다.",
        "search_hub": {
            "h2": "포케후타 찾기",
            "card_pref_title": "도도부현으로 찾기",
            "card_pref_desc": "47개 도도부현 설치 수량 일람",
            "card_pokemon_title": "포켓몬으로 찾기",
            "card_pokemon_desc": "포켓몬 종류별 일람",
            "card_map_title": "지도에서 찾기",
            "card_map_desc": "인터랙티브 지도로 확인",
        },
        "popular_pokemon": {
            "h2": "인기 포켓몬 포케후타",
        },
        "pokemon_ranking": {
            "h2": "포켓몬 랭킹",
            "h3_count": "포케후타 수 랭킹",
            "h3_pref": "등장 시구정촌 수 랭킹",
            "pref_count_unit": "개 시구정촌",
        },
    },
}

_CSS = """\
    body {
      margin: 0;
      background: #f7f0df;
      color: #201b16;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.7;
    }

    .summary-page {
      max-width: 1040px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }

    .summary-hero {
      padding: 28px 0 18px;
    }

    .summary-hero a,
    .summary-link {
      color: #176f68;
      font-weight: 850;
      text-decoration: none;
    }

    .summary-hero h1 {
      margin: 8px 0 10px;
      font-size: clamp(2rem, 7vw, 3.4rem);
      line-height: 1.12;
      letter-spacing: 0;
    }

    .summary-hero p {
      max-width: 720px;
      margin: 0;
      color: #574b41;
      font-size: 1rem;
      font-weight: 650;
    }

    .summary-stats {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin: 20px 0 24px;
    }

    .summary-stat {
      padding: 16px;
      border: 1px solid rgba(93, 67, 35, .16);
      border-radius: 8px;
      background: #fffaf0;
    }

    .summary-stat span {
      display: block;
      color: #716154;
      font-size: .84rem;
      font-weight: 800;
    }

    .summary-stat strong {
      display: block;
      margin-top: 4px;
      font-size: 2rem;
      line-height: 1.1;
    }

    .daily-fact-card {
      display: grid;
      gap: 14px;
      margin: 0 0 22px;
      padding: 18px;
      border: 1px solid rgba(23, 111, 104, .24);
      border-radius: 8px;
      background: #fffdf7;
      box-shadow: 0 14px 30px rgba(54, 40, 22, .08);
    }

    .daily-fact-label {
      display: inline-flex;
      width: fit-content;
      padding: 3px 9px;
      border-radius: 999px;
      background: #e5f4f2;
      color: #176f68;
      font-size: .8rem;
      font-weight: 900;
    }

    .daily-fact-card h2 {
      margin: 0;
    }

    .daily-fact-card strong {
      display: block;
      max-width: 760px;
      font-size: clamp(1.45rem, 6vw, 2.35rem);
      line-height: 1.22;
      letter-spacing: 0;
    }

    .daily-fact-card p {
      margin: 0;
      color: #574b41;
      font-weight: 750;
    }

    .summary-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }

    .summary-action {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
      padding: 0 14px;
      border-radius: 8px;
      background: #176f68;
      color: #fff;
      font-size: .9rem;
      font-weight: 900;
      text-decoration: none;
    }

    .summary-action.secondary {
      background: #fff6e6;
      color: #176f68;
      border: 1px solid rgba(23, 111, 104, .22);
    }

    .fact-card-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 12px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .fact-card-grid > li {
      display: flex;
      min-width: 0;
    }

    .summary-fact-card {
      display: flex;
      flex-direction: column;
      gap: 10px;
      width: 100%;
      padding: 15px;
      border: 1px solid rgba(93, 67, 35, .14);
      border-radius: 8px;
      background: #fffdf7;
    }

    .summary-fact-card h3 {
      margin: 0;
      font-size: 1.05rem;
      line-height: 1.35;
      letter-spacing: 0;
    }

    .summary-fact-number {
      display: block;
      color: #176f68;
      font-size: 2.1rem;
      font-weight: 950;
      line-height: 1;
    }

    .summary-fact-main,
    .summary-fact-note {
      margin: 0;
      color: #574b41;
      font-size: .92rem;
      font-weight: 750;
      line-height: 1.65;
    }

    .summary-fact-note {
      color: #716154;
      font-size: .84rem;
    }

    .summary-fact-card .summary-actions {
      margin-top: auto;
    }

    .summary-section {
      margin-top: 28px;
    }

    .summary-section h2 {
      margin: 0 0 10px;
      font-size: 1.35rem;
      letter-spacing: 0;
    }

    .summary-table-wrap {
      overflow-x: auto;
      border: 1px solid rgba(93, 67, 35, .16);
      border-radius: 8px;
      background: #fffdf7;
    }

    table {
      width: 100%;
      min-width: 520px;
      border-collapse: collapse;
    }

    th,
    td {
      padding: 11px 12px;
      border-bottom: 1px solid rgba(93, 67, 35, .11);
      text-align: left;
    }

    th {
      background: #fff6e6;
      font-size: .84rem;
      font-weight: 900;
    }

    tr:last-child td {
      border-bottom: 0;
    }

    .summary-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .summary-list li,
    .summary-empty {
      padding: 12px;
      border: 1px solid rgba(93, 67, 35, .14);
      border-radius: 8px;
      background: #fffaf0;
      font-weight: 800;
    }

    .summary-list small {
      display: block;
      color: #6d5f55;
      font-weight: 750;
    }

    .summary-cta {
      display: inline-flex;
      align-items: center;
      min-height: 44px;
      margin-top: 10px;
      padding: 0 16px;
      border-radius: 8px;
      background: #176f68;
      color: #fff;
      font-weight: 900;
      text-decoration: none;
    }

    .ai-summary-box {
      margin: 0 0 20px;
      padding: 16px 18px;
      background: #f0faf9;
      border-left: 4px solid #176f68;
      border-radius: 0 8px 8px 0;
      font-size: 1rem;
      color: #2d5c58;
      line-height: 1.8;
    }

    .discovery-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .discovery-card {
      padding: 14px;
      border: 1px solid rgba(93, 67, 35, .14);
      border-radius: 8px;
      background: #fffdf7;
    }

    .discovery-card strong {
      display: block;
      font-size: 1.25rem;
      line-height: 1.2;
      margin-bottom: 4px;
      color: #176f68;
    }

    .discovery-card span {
      display: block;
      font-size: .84rem;
      color: #5a4f47;
      font-weight: 750;
    }

    .regional-trend-box {
      padding: 14px 16px;
      border: 1px solid rgba(93, 67, 35, .14);
      border-radius: 8px;
      background: #fffaf0;
      font-size: .95rem;
      color: #574b41;
      line-height: 1.8;
    }

    .empty-note {
      margin-top: 10px;
      font-size: .9rem;
      color: #716154;
      line-height: 1.75;
    }

    .summary-list li a.summary-link {
      font-size: .78rem;
      margin-left: 6px;
    }

    .search-hub-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin: 18px 0 0;
    }

    .search-hub-card {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 18px 14px;
      background: #fffaf0;
      border: 1px solid rgba(23, 111, 104, .24);
      border-radius: 8px;
      text-decoration: none;
      color: inherit;
    }

    .search-hub-card:hover {
      background: #e5f4f2;
    }

    .search-hub-card strong {
      color: #176f68;
      font-size: 1rem;
      font-weight: 900;
    }

    .search-hub-card span {
      color: #574b41;
      font-size: .875rem;
    }

    .pokemon-popular-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin: 12px 0 0;
    }

    .pokemon-card {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 12px;
      background: #fffaf0;
      border: 1px solid rgba(93, 67, 35, .14);
      border-radius: 8px;
      text-decoration: none;
      color: inherit;
    }

    .pokemon-card:hover {
      background: #e5f4f2;
    }

    .pokemon-card strong {
      font-size: .95rem;
      font-weight: 850;
    }

    .pokemon-card span {
      color: #574b41;
      font-size: .84rem;
    }

    .photos-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin: 12px 0 0;
    }

    .photo-card {
      display: flex;
      flex-direction: column;
      gap: 5px;
      text-decoration: none;
      color: inherit;
    }

    .photo-card img {
      width: 100%;
      aspect-ratio: 4 / 3;
      object-fit: contain;
      background: #fffaf0;
      border-radius: 6px;
      border: 1px solid rgba(93, 67, 35, .12);
    }

    .photo-card-title {
      font-size: .84rem;
      font-weight: 800;
      line-height: 1.35;
    }

    .photo-card-meta {
      font-size: .76rem;
      color: #716154;
    }

    .pokemon-ranking-cols {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-top: 12px;
    }

    .pokemon-ranking-cols h3 {
      margin: 0 0 8px;
      font-size: 1rem;
      font-weight: 900;
    }

    .section-note {
      margin: 6px 0 0;
      font-size: .9rem;
      color: #574b41;
      line-height: 1.7;
    }

    @media (max-width: 700px) {
      .summary-stats {
        grid-template-columns: 1fr;
      }

      .summary-hero h1 {
        font-size: 2rem;
      }

      .discovery-grid {
        grid-template-columns: repeat(2, 1fr);
      }

      .fact-card-grid {
        grid-template-columns: 1fr;
      }

      .search-hub-grid {
        grid-template-columns: 1fr;
      }

      .pokemon-popular-grid {
        grid-template-columns: repeat(2, 1fr);
      }

      .photos-grid {
        grid-template-columns: repeat(2, 1fr);
      }

      .pokemon-ranking-cols {
        grid-template-columns: 1fr;
      }
    }"""

_HREFLANG = """\
  <link rel="alternate" hreflang="ja"      href="https://data.pokefuta.com/summary">
  <link rel="alternate" hreflang="en"      href="https://data.pokefuta.com/en/summary">
  <link rel="alternate" hreflang="zh-TW"   href="https://data.pokefuta.com/zh-TW/summary">
  <link rel="alternate" hreflang="zh-Hans" href="https://data.pokefuta.com/zh-CN/summary">
  <link rel="alternate" hreflang="ko"      href="https://data.pokefuta.com/ko/summary">
  <link rel="alternate" hreflang="x-default" href="https://data.pokefuta.com/summary">"""


def load_records(path: Path) -> list[dict]:
    by_id: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            record_id = str(record.get("id", "")).strip()
            if not record_id:
                continue
            by_id[record_id] = {**by_id.get(record_id, {}), **record}
    return list(by_id.values())


def build_stats(records: list[dict]) -> dict:
    counts: dict[str, int] = {pref: 0 for pref in PREFECTURE_ORDER}
    for record in records:
        pref = record.get("prefecture", "")
        if pref in counts:
            counts[pref] += 1

    by_pref = [{"pref": p, "count": counts[p]} for p in PREFECTURE_ORDER]
    total = sum(item["count"] for item in by_pref)
    installed = [item for item in by_pref if item["count"] > 0]
    empty = [item for item in by_pref if item["count"] == 0]
    ranking = sorted(
        installed,
        key=lambda x: (-x["count"], PREFECTURE_ORDER.index(x["pref"])),
    )[:10]

    regional: dict[str, int] = {}
    for pref, count in counts.items():
        region = REGION_MAP.get(pref, "その他")
        regional[region] = regional.get(region, 0) + count

    return {
        "total": total,
        "by_pref": by_pref,
        "ranking": ranking,
        "empty": empty,
        "installed": installed,
        "regional": regional,
    }


def _build_ai_summary(s: dict, stats: dict, tr) -> str:
    total = stats["total"]
    ranking = stats["ranking"]
    empty = stats["empty"]
    if not ranking:
        return ""

    top1 = ranking[0]
    top3 = "・".join(tr(r["pref"]) for r in ranking[:3])
    text = s["ai_intro"].format(total=total)
    text += s["ai_top"].format(
        top1pref=tr(top1["pref"]), top1count=top1["count"], top3=top3
    )
    if empty:
        text += s["ai_empty"].format(empty_count=len(empty))
    text += s["ai_outro"]
    return f'<div class="ai-summary-box"><p>{escape(text)}</p></div>\n'


def _build_discovery_section(s: dict, stats: dict, tr) -> str:
    total = stats["total"]
    installed = stats["installed"]
    ranking = stats["ranking"]
    empty = stats["empty"]
    if not ranking or not total:
        return ""

    top1 = ranking[0]
    avg = round(total / len(installed)) if installed else 0
    pct = round((top1["count"] / total) * 100)
    count_unit = s["count_unit"]

    cards = [
        {
            "stat": f"{top1['count']}{count_unit}",
            "desc": s["disc_top_pct"].format(pref=tr(top1["pref"]), pct=pct),
        },
        {
            "stat": s["installed_fmt"].format(count=len(installed)),
            "desc": s["disc_installed"],
        },
        {
            "stat": f"{avg}{count_unit}",
            "desc": s["disc_avg"],
        },
    ]
    if empty:
        cards.append({
            "stat": s["empty_fmt"].format(count=len(empty)),
            "desc": s["disc_empty"],
        })

    items = "\n        ".join(
        f'<li class="discovery-card">'
        f'<strong>{escape(c["stat"])}</strong>'
        f'<span>{escape(c["desc"])}</span>'
        f'</li>'
        for c in cards
    )
    return (
        f'\n    <section class="summary-section" aria-label="{escape(s["discovery_aria"])}">'
        f'\n      <ul class="discovery-grid">\n        {items}\n      </ul>'
        f'\n    </section>\n'
    )


def _twitter_intent_url(text: str, url: str) -> str:
    return (
        "https://twitter.com/intent/tweet"
        f"?text={quote(text, safe='')}"
        f"&url={quote(url, safe='')}"
    )


def _map_href(map_base: str, pref_ja: str | None = None) -> str:
    return f"{map_base}?pref={quote(pref_ja)}" if pref_ja else map_base


def _track_attrs(event_name: str, fact: dict, target_url: str) -> str:
    return (
        f'data-summary-event="{escape(event_name)}" '
        f'data-fact-id="{escape(fact["id"])}" '
        f'data-fact-title="{escape(fact["title"])}" '
        f'data-image-type="{escape(fact["image_type"])}" '
        f'data-target-url="{escape(target_url)}"'
    )


def _top_rank_context(stats: dict) -> dict[str, str | int]:
    ranking = stats["ranking"]
    fallback = {"pref": "ポケふた設置県", "count": 0}
    top1 = ranking[0] if len(ranking) > 0 else fallback
    top2 = ranking[1] if len(ranking) > 1 else top1
    top3 = ranking[2] if len(ranking) > 2 else top2
    return {
        "total": stats["total"],
        "top1pref": top1["pref"],
        "top1count": top1["count"],
        "top2pref": top2["pref"],
        "top2count": top2["count"],
        "top3pref": top3["pref"],
        "top3count": top3["count"],
    }


def _format_summary_text(value: str, s: dict, stats: dict) -> str:
    if s.get("pref_key") != "ja":
        return value
    return value.format(**_top_rank_context(stats))


FACT_COPY: dict[str, dict] = {
    "ja": {
        "daily": "今日のポケふた雑学",
        "section": "ポケふた雑学",
        "share": "Xで共有",
        "hashtags": ["#ポケふた", "#ポケモンマンホール"],
        "empty_status": "まだ{empty_count}県には設置されていません。",
        "empty_share_lead": "まだ設置されていない県は{empty_count}県あります。",
        "empty_image_subtitle": "未設置は{empty_count}県",
        "all_installed_status": "すべての都道府県に設置されています。",
        "all_installed_share_lead": "すべての都道府県にポケふたがあります。",
        "all_installed_image_subtitle": "全都道府県に設置済み",
        "list_separator": "・",
        "top3_separator": "・",
        "map_all": "全国マップを見る",
        "map_rank": "ランキングを見る",
        "map_pref": "{pref}を地図で見る",
        "facts": {
            "hokkaido": {
                "type": "prefecture_rank",
                "title": "{hokkaido_name}だけで{hokkaido}枚",
                "stat": "{hokkaido}枚",
                "main": "{hokkaido_name}には{hokkaido}枚のポケふたがあります。全国{total}枚の約{hokkaido_pct}%です。",
                "note": "広い北海道では、ポケふた巡りも立派な旅になります。",
                "share_title": "{hokkaido_name}だけでポケふたは{hokkaido}枚。",
                "share_lead": "全国{total}枚の約{hokkaido_pct}%が北海道にあります。",
                "share_body": "地域ごとの数を眺めると、旅の行き先候補も少し変わって見えます。",
                "image_type": "summary_prefecture_rank",
                "image_title": "{hokkaido_name}だけで{hokkaido}枚",
                "image_main_value": "{hokkaido}枚",
                "image_subtitle": "全国の約{hokkaido_pct}%",
                "image_footer": "ポケふた都道府県別ランキング",
                "map_pref": "北海道",
            },
            "installed-prefectures": {
                "type": "travel_trivia",
                "title": "設置済みは{installed_count}都道府県",
                "stat": "{installed_count}都道府県",
                "main": "ポケふた設置済みは{installed_count}都道府県。{empty_status}",
                "note": "全国に広がりつつも、まだ空白地帯があります。",
                "share_title": "ポケふた設置済みは{installed_count}都道府県。",
                "share_lead": "{empty_share_lead}",
                "share_body": "全国{total}枚の分布を一覧で見ると、まだ出会っていない地域が見つかります。",
                "image_type": "summary_installed_prefectures",
                "image_title": "ポケふた設置済み",
                "image_main_value": "{installed_count}都道府県",
                "image_subtitle": "{empty_image_subtitle}",
                "image_footer": "全国{total}枚のポケふた一覧",
            },
            "tohoku": {
                "type": "regional_density",
                "title": "{tohoku_name}は{tohoku}枚の密集エリア",
                "stat": "{tohoku}枚",
                "main": "{tohoku_name}地方には{tohoku}枚のポケふたがあります。全国でも特に密度の高いエリアです。",
                "note": "福島県、宮城県、岩手県など、巡りがいのある県が並びます。",
                "share_title": "{tohoku_name}地方にはポケふたが{tohoku}枚。",
                "share_lead": "福島県・宮城県・岩手県など、旅で巡りやすい密集エリアです。",
                "share_body": "東北旅行の目的地選びにも使いやすい数字です。",
                "image_type": "summary_regional_density",
                "image_title": "{tohoku_name}は密集エリア",
                "image_main_value": "{tohoku}枚",
                "image_subtitle": "福島・宮城・岩手に多く分布",
                "image_footer": "地域別のポケふた分布",
            },
            "top-prefectures": {
                "type": "prefecture_rank",
                "title": "多い県トップ3",
                "stat": "TOP3",
                "main": "ポケふたが多い県トップ3は、{top3}です。",
                "note": "上位は北日本の存在感が大きめです。",
                "share_title": "ポケふたが多い都道府県トップ3。",
                "share_lead": "{top3}が上位です。",
                "share_body": "数字で見ると、次の旅行先候補がかなり具体的になります。",
                "image_type": "summary_top_prefectures",
                "image_title": "多い県トップ3",
                "image_main_value": "TOP3",
                "image_subtitle": "{top3}",
                "image_footer": "ポケふた都道府県別ランキング",
                "map_label_key": "map_rank",
            },
            "fukushima": {
                "type": "prefecture_rank",
                "title": "{fukushima_name}は全国2位",
                "stat": "{fukushima}枚",
                "main": "{fukushima_name}には{fukushima}枚のポケふたがあります。北海道に次ぐ全国2位です。",
                "note": "県内を巡るだけでも、かなり濃いポケふた旅になります。",
                "share_title": "{fukushima_name}のポケふたは{fukushima}枚。",
                "share_lead": "北海道に次ぐ全国2位です。",
                "share_body": "1県の中だけでも、しっかり巡る旅が成立する数です。",
                "image_type": "summary_prefecture_rank",
                "image_title": "{fukushima_name}は全国2位",
                "image_main_value": "{fukushima}枚",
                "image_subtitle": "北海道に次ぐ設置数",
                "image_footer": "ポケふた都道府県別ランキング",
                "map_pref": "福島県",
            },
            "miyagi-iwate": {
                "type": "regional_density",
                "title": "{miyagi_name}と{iwate_name}も強い",
                "stat": "{miyagi}+{iwate}枚",
                "main": "{miyagi_name}には{miyagi}枚、{iwate_name}には{iwate}枚。東北はポケふた巡りの有力エリアです。",
                "note": "東北旅行の目的地選びにも使いやすい数字です。",
                "share_title": "{miyagi_name}{miyagi}枚、{iwate_name}{iwate}枚。",
                "share_lead": "東北はポケふた巡りの有力エリアです。",
                "share_body": "地域をまたいで巡ると、旅程そのものがポケふた探しになります。",
                "image_type": "summary_regional_pair",
                "image_title": "{miyagi_name}と{iwate_name}",
                "image_main_value": "{miyagi}+{iwate}枚",
                "image_subtitle": "東北旅行で巡りたいエリア",
                "image_footer": "地域別のポケふた分布",
                "map_pref": "宮城県",
            },
            "mie": {
                "type": "prefecture_rank",
                "title": "{mie_name}は{mie}枚",
                "stat": "{mie}枚",
                "main": "{mie_name}には{mie}枚のポケふたがあります。近畿・東海エリアでも存在感があります。",
                "note": "関西・東海方面の旅程にも組み込みやすい地域です。",
                "share_title": "{mie_name}にはポケふたが{mie}枚。",
                "share_lead": "近畿・東海エリアでも存在感のある設置数です。",
                "share_body": "移動ルートに組み込むと、旅の寄り道が少し楽しくなります。",
                "image_type": "summary_prefecture_rank",
                "image_title": "{mie_name}は{mie}枚",
                "image_main_value": "{mie}枚",
                "image_subtitle": "近畿・東海エリアの注目県",
                "image_footer": "ポケふた都道府県別ランキング",
                "map_pref": "三重県",
            },
            "empty-prefectures": {
                "type": "travel_trivia",
                "title": "まだポケふたがない県",
                "stat": "{empty_count}県",
                "main": "{empty_names}には、まだポケふたがありません。",
                "note": "次にどこへ広がるのかを予想する楽しみもあります。",
                "share_title": "まだポケふたがない県は{empty_count}県。",
                "share_lead": "{empty_names}です。",
                "share_body": "全国{total}枚の一覧を見ると、空白地帯にも地域の個性が見えてきます。",
                "image_type": "summary_empty_prefectures",
                "image_title": "まだポケふたがない県",
                "image_main_value": "{empty_count}県",
                "image_subtitle": "{empty_names}",
                "image_footer": "全国{total}枚のポケふた一覧",
            },
        },
    },
    "en": {
        "daily": "Today's Pokefuta Trivia",
        "section": "Pokefuta Trivia",
        "share": "Share on X",
        "hashtags": ["#Pokefuta", "#PokemonManhole"],
        "empty_status": "{empty_count} prefectures still have none.",
        "empty_share_lead": "{empty_count} prefectures still have no Pokefuta.",
        "empty_image_subtitle": "{empty_count} still without one",
        "all_installed_status": "Every prefecture now has Pokefuta.",
        "all_installed_share_lead": "All prefectures now have Pokefuta.",
        "all_installed_image_subtitle": "all prefectures covered",
        "list_separator": ", ",
        "top3_separator": ", ",
        "map_all": "View the Japan map",
        "map_rank": "View rankings",
        "map_pref": "View {pref} on the map",
        "facts": {
            "hokkaido": {
                "type": "prefecture_rank",
                "title": "{hokkaido_name} alone has {hokkaido}",
                "stat": "{hokkaido}",
                "main": "{hokkaido_name} has {hokkaido} Pokefuta, about {hokkaido_pct}% of the nationwide total of {total}.",
                "note": "In wide-open Hokkaido, collecting Pokefuta can become a trip in itself.",
                "share_title": "{hokkaido_name} alone has {hokkaido} Pokefuta.",
                "share_lead": "That is about {hokkaido_pct}% of Japan's {total} total.",
                "share_body": "The prefecture counts make travel ideas feel surprisingly concrete.",
                "image_type": "summary_prefecture_rank",
                "image_title": "{hokkaido_name} alone",
                "image_main_value": "{hokkaido}",
                "image_subtitle": "about {hokkaido_pct}% nationwide",
                "image_footer": "Pokefuta ranking by prefecture",
                "map_pref": "北海道",
            },
            "installed-prefectures": {
                "type": "travel_trivia",
                "title": "{installed_count} prefectures have Pokefuta",
                "stat": "{installed_count}",
                "main": "Pokefuta are installed in {installed_count} prefectures. {empty_status}",
                "note": "They have spread across Japan, while a few blank spots remain.",
                "share_title": "Pokefuta are in {installed_count} prefectures.",
                "share_lead": "{empty_share_lead}",
                "share_body": "A nationwide list makes the next region to explore easier to spot.",
                "image_type": "summary_installed_prefectures",
                "image_title": "Prefectures with Pokefuta",
                "image_main_value": "{installed_count}",
                "image_subtitle": "{empty_image_subtitle}",
                "image_footer": "Nationwide Pokefuta list",
            },
            "tohoku": {
                "type": "regional_density",
                "title": "{tohoku_name}: {tohoku} in one region",
                "stat": "{tohoku}",
                "main": "{tohoku_name} has {tohoku} Pokefuta, one of the densest regions nationwide.",
                "note": "Fukushima, Miyagi, and Iwate make this area especially rewarding to explore.",
                "share_title": "{tohoku_name} has {tohoku} Pokefuta.",
                "share_lead": "Fukushima, Miyagi, and Iwate make it a strong travel area.",
                "share_body": "It is a useful number when choosing where to go next.",
                "image_type": "summary_regional_density",
                "image_title": "{tohoku_name} density",
                "image_main_value": "{tohoku}",
                "image_subtitle": "Many in Fukushima, Miyagi, and Iwate",
                "image_footer": "Regional Pokefuta distribution",
            },
            "top-prefectures": {
                "type": "prefecture_rank",
                "title": "Top 3 prefectures",
                "stat": "TOP 3",
                "main": "The top 3 prefectures by Pokefuta count are {top3}.",
                "note": "Northern Japan has a strong presence near the top.",
                "share_title": "Top 3 prefectures by Pokefuta count.",
                "share_lead": "{top3} lead the ranking.",
                "share_body": "Numbers like these can turn a map into a travel shortlist.",
                "image_type": "summary_top_prefectures",
                "image_title": "Top 3 prefectures",
                "image_main_value": "TOP 3",
                "image_subtitle": "{top3}",
                "image_footer": "Pokefuta ranking by prefecture",
                "map_label_key": "map_rank",
            },
            "fukushima": {
                "type": "prefecture_rank",
                "title": "{fukushima_name} ranks #2",
                "stat": "{fukushima}",
                "main": "{fukushima_name} has {fukushima} Pokefuta, second only to Hokkaido.",
                "note": "A trip within the prefecture alone can be rich with discoveries.",
                "share_title": "{fukushima_name} has {fukushima} Pokefuta.",
                "share_lead": "That puts it second nationwide after Hokkaido.",
                "share_body": "It is enough for a full local Pokefuta trip.",
                "image_type": "summary_prefecture_rank",
                "image_title": "{fukushima_name} ranks #2",
                "image_main_value": "{fukushima}",
                "image_subtitle": "second only to Hokkaido",
                "image_footer": "Pokefuta ranking by prefecture",
                "map_pref": "福島県",
            },
            "miyagi-iwate": {
                "type": "regional_density",
                "title": "{miyagi_name} and {iwate_name} are strong too",
                "stat": "{miyagi}+{iwate}",
                "main": "{miyagi_name} has {miyagi}, and {iwate_name} has {iwate}. Tohoku is a major Pokefuta travel area.",
                "note": "These numbers are useful when planning a Tohoku route.",
                "share_title": "{miyagi_name}: {miyagi}, {iwate_name}: {iwate}.",
                "share_lead": "Tohoku is one of the strongest areas for Pokefuta trips.",
                "share_body": "Crossing prefectures can make the route itself part of the fun.",
                "image_type": "summary_regional_pair",
                "image_title": "{miyagi_name} and {iwate_name}",
                "image_main_value": "{miyagi}+{iwate}",
                "image_subtitle": "a Tohoku travel route idea",
                "image_footer": "Regional Pokefuta distribution",
                "map_pref": "宮城県",
            },
            "mie": {
                "type": "prefecture_rank",
                "title": "{mie_name} has {mie}",
                "stat": "{mie}",
                "main": "{mie_name} has {mie} Pokefuta, giving it a clear presence in the Kinki-Tokai area.",
                "note": "It is easy to fold into a Kansai or Tokai travel plan.",
                "share_title": "{mie_name} has {mie} Pokefuta.",
                "share_lead": "It stands out in the Kinki-Tokai area.",
                "share_body": "A small detour can become part of the discovery.",
                "image_type": "summary_prefecture_rank",
                "image_title": "{mie_name} has {mie}",
                "image_main_value": "{mie}",
                "image_subtitle": "Kinki-Tokai area highlight",
                "image_footer": "Pokefuta ranking by prefecture",
                "map_pref": "三重県",
            },
            "empty-prefectures": {
                "type": "travel_trivia",
                "title": "Prefectures still without Pokefuta",
                "stat": "{empty_count}",
                "main": "{empty_names} still have no Pokefuta.",
                "note": "Guessing where the next one may appear is part of the fun.",
                "share_title": "{empty_count} prefectures still have no Pokefuta.",
                "share_lead": "They are {empty_names}.",
                "share_body": "A nationwide list shows both the spread and the remaining blank spots.",
                "image_type": "summary_empty_prefectures",
                "image_title": "Still no Pokefuta",
                "image_main_value": "{empty_count}",
                "image_subtitle": "{empty_names}",
                "image_footer": "Nationwide Pokefuta list",
            },
        },
    },
}

FACT_COPY["zh-CN"] = {
    **FACT_COPY["en"],
    "daily": "今日宝可梦井盖小知识",
    "section": "宝可梦井盖小知识",
    "share": "分享到 X",
    "hashtags": ["#Pokefuta", "#PokemonManhole"],
    "empty_status": "仍有{empty_count}个县尚未设置。",
    "empty_share_lead": "仍有{empty_count}个县没有宝可梦井盖。",
    "empty_image_subtitle": "未设置为{empty_count}县",
    "all_installed_status": "所有都道府县都已设置宝可梦井盖。",
    "all_installed_share_lead": "所有都道府县现在都有宝可梦井盖。",
    "all_installed_image_subtitle": "所有都道府县均已设置",
    "list_separator": "、",
    "top3_separator": "、",
    "map_all": "查看全国地图",
    "map_rank": "查看排行榜",
    "map_pref": "在地图上查看{pref}",
}
FACT_COPY["zh-TW"] = {
    **FACT_COPY["zh-CN"],
    "daily": "今日寶可夢人孔蓋小知識",
    "section": "寶可夢人孔蓋小知識",
    "empty_status": "仍有{empty_count}個縣尚未設置。",
    "empty_share_lead": "仍有{empty_count}個縣沒有寶可夢人孔蓋。",
    "empty_image_subtitle": "未設置為{empty_count}縣",
    "all_installed_status": "所有都道府縣都已設置寶可夢人孔蓋。",
    "all_installed_share_lead": "所有都道府縣現在都有寶可夢人孔蓋。",
    "all_installed_image_subtitle": "所有都道府縣均已設置",
    "map_all": "查看全國地圖",
    "map_rank": "查看排行榜",
    "map_pref": "在地圖上查看{pref}",
}
FACT_COPY["ko"] = {
    **FACT_COPY["en"],
    "daily": "오늘의 포케후타 상식",
    "section": "포케후타 상식",
    "share": "X에 공유",
    "hashtags": ["#Pokefuta", "#PokemonManhole"],
    "empty_status": "아직 {empty_count}개 현에는 설치되어 있지 않습니다.",
    "empty_share_lead": "아직 포케후타가 없는 현은 {empty_count}곳입니다.",
    "empty_image_subtitle": "미설치는 {empty_count}개 현",
    "all_installed_status": "모든 도도부현에 포케후타가 설치되어 있습니다.",
    "all_installed_share_lead": "모든 도도부현에서 포케후타를 만날 수 있습니다.",
    "all_installed_image_subtitle": "모든 도도부현 설치 완료",
    "list_separator": "・",
    "top3_separator": "・",
    "map_all": "전국 지도 보기",
    "map_rank": "랭킹 보기",
    "map_pref": "지도에서 {pref} 보기",
}

FACT_COPY["zh-CN"]["facts"] = {
    "hokkaido": {
        "type": "prefecture_rank",
        "title": "仅{hokkaido_name}就有{hokkaido}个",
        "stat": "{hokkaido}个",
        "main": "{hokkaido_name}有{hokkaido}个宝可梦井盖，约占全国{total}个的{hokkaido_pct}%。",
        "note": "在辽阔的北海道，寻找宝可梦井盖本身就能成为一趟旅行。",
        "share_title": "{hokkaido_name}一个地区就有{hokkaido}个宝可梦井盖。",
        "share_lead": "约占全国{total}个的{hokkaido_pct}%。",
        "share_body": "按都道府县看数量，旅行目的地也会变得更具体。",
        "image_type": "summary_prefecture_rank",
        "image_title": "{hokkaido_name}就有{hokkaido}个",
        "image_main_value": "{hokkaido}个",
        "image_subtitle": "约占全国{hokkaido_pct}%",
        "image_footer": "宝可梦井盖都道府县排行榜",
        "map_pref": "北海道",
    },
    "installed-prefectures": {
        "type": "travel_trivia",
        "title": "已设置{installed_count}个都道府县",
        "stat": "{installed_count}个都道府县",
        "main": "宝可梦井盖已设置于{installed_count}个都道府县。{empty_status}",
        "note": "虽然已经遍布日本各地，但仍然有空白区域。",
        "share_title": "宝可梦井盖已设置于{installed_count}个都道府县。",
        "share_lead": "{empty_share_lead}",
        "share_body": "查看全国{total}个分布，就能发现还没遇见的地区。",
        "image_type": "summary_installed_prefectures",
        "image_title": "已设置宝可梦井盖",
        "image_main_value": "{installed_count}个都道府县",
        "image_subtitle": "{empty_image_subtitle}",
        "image_footer": "全国{total}个宝可梦井盖一览",
    },
    "tohoku": {
        "type": "regional_density",
        "title": "{tohoku_name}是{tohoku}个的密集区域",
        "stat": "{tohoku}个",
        "main": "{tohoku_name}地区有{tohoku}个宝可梦井盖，是全国密度较高的区域之一。",
        "note": "福岛县、宫城县、岩手县等地都很值得巡游。",
        "share_title": "{tohoku_name}地区有{tohoku}个宝可梦井盖。",
        "share_lead": "福岛、宫城、岩手等地，是很适合旅行巡游的密集区域。",
        "share_body": "规划东北旅行时，这个数字很有参考价值。",
        "image_type": "summary_regional_density",
        "image_title": "{tohoku_name}密集区域",
        "image_main_value": "{tohoku}个",
        "image_subtitle": "福岛・宫城・岩手分布较多",
        "image_footer": "宝可梦井盖地区分布",
    },
    "top-prefectures": {
        "type": "prefecture_rank",
        "title": "数量最多的前三名",
        "stat": "TOP3",
        "main": "宝可梦井盖数量最多的前三名是：{top3}。",
        "note": "北日本地区在上位榜单中存在感很强。",
        "share_title": "宝可梦井盖数量最多的都道府县TOP3。",
        "share_lead": "{top3}位居前列。",
        "share_body": "把地图换成数字来看，下一趟旅行的候选地会更清楚。",
        "image_type": "summary_top_prefectures",
        "image_title": "数量最多TOP3",
        "image_main_value": "TOP3",
        "image_subtitle": "{top3}",
        "image_footer": "宝可梦井盖都道府县排行榜",
        "map_label_key": "map_rank",
    },
    "fukushima": {
        "type": "prefecture_rank",
        "title": "{fukushima_name}位居全国第2",
        "stat": "{fukushima}个",
        "main": "{fukushima_name}有{fukushima}个宝可梦井盖，仅次于北海道，位居全国第2。",
        "note": "只在县内巡游，也能是一趟内容很丰富的宝可梦井盖之旅。",
        "share_title": "{fukushima_name}有{fukushima}个宝可梦井盖。",
        "share_lead": "仅次于北海道，位居全国第2。",
        "share_body": "这个数量足以支撑一趟县内巡游。",
        "image_type": "summary_prefecture_rank",
        "image_title": "{fukushima_name}全国第2",
        "image_main_value": "{fukushima}个",
        "image_subtitle": "仅次于北海道",
        "image_footer": "宝可梦井盖都道府县排行榜",
        "map_pref": "福島県",
    },
    "miyagi-iwate": {
        "type": "regional_density",
        "title": "{miyagi_name}和{iwate_name}也很强",
        "stat": "{miyagi}+{iwate}个",
        "main": "{miyagi_name}有{miyagi}个，{iwate_name}有{iwate}个。东北是宝可梦井盖巡游的重要区域。",
        "note": "这些数字也很适合用来规划东北旅行。",
        "share_title": "{miyagi_name}{miyagi}个，{iwate_name}{iwate}个。",
        "share_lead": "东北是宝可梦井盖巡游的强势区域。",
        "share_body": "跨县巡游时，路线本身也会变成旅行的乐趣。",
        "image_type": "summary_regional_pair",
        "image_title": "{miyagi_name}和{iwate_name}",
        "image_main_value": "{miyagi}+{iwate}个",
        "image_subtitle": "东北旅行巡游候选",
        "image_footer": "宝可梦井盖地区分布",
        "map_pref": "宮城県",
    },
    "mie": {
        "type": "prefecture_rank",
        "title": "{mie_name}有{mie}个",
        "stat": "{mie}个",
        "main": "{mie_name}有{mie}个宝可梦井盖，在近畿・东海区域也很有存在感。",
        "note": "很适合加入关西或东海方向的旅行路线。",
        "share_title": "{mie_name}有{mie}个宝可梦井盖。",
        "share_lead": "在近畿・东海区域也很有存在感。",
        "share_body": "把它作为顺路停靠点，旅行会多一点发现感。",
        "image_type": "summary_prefecture_rank",
        "image_title": "{mie_name}有{mie}个",
        "image_main_value": "{mie}个",
        "image_subtitle": "近畿・东海区域的注目县",
        "image_footer": "宝可梦井盖都道府县排行榜",
        "map_pref": "三重県",
    },
    "empty-prefectures": {
        "type": "travel_trivia",
        "title": "仍没有宝可梦井盖的县",
        "stat": "{empty_count}县",
        "main": "{empty_names}仍然没有宝可梦井盖。",
        "note": "猜测下一处会设置在哪里，也是乐趣之一。",
        "share_title": "仍没有宝可梦井盖的县有{empty_count}个。",
        "share_lead": "分别是{empty_names}。",
        "share_body": "全国{total}个一览能同时看到扩展范围和空白区域。",
        "image_type": "summary_empty_prefectures",
        "image_title": "仍没有宝可梦井盖的县",
        "image_main_value": "{empty_count}县",
        "image_subtitle": "{empty_names}",
        "image_footer": "全国{total}个宝可梦井盖一览",
    },
}
FACT_COPY["zh-TW"]["facts"] = {
    "hokkaido": {
        "type": "prefecture_rank",
        "title": "光是{hokkaido_name}就有{hokkaido}個",
        "stat": "{hokkaido}個",
        "main": "{hokkaido_name}有{hokkaido}個寶可夢人孔蓋，約占全國{total}個的{hokkaido_pct}%。",
        "note": "在幅員遼闊的北海道，尋找寶可夢人孔蓋本身就是一趟旅行。",
        "share_title": "{hokkaido_name}一地就有{hokkaido}個寶可夢人孔蓋。",
        "share_lead": "約占全國{total}個的{hokkaido_pct}%。",
        "share_body": "用都道府縣別數字來看，下一趟旅行的候選地會更具體。",
        "image_type": "summary_prefecture_rank",
        "image_title": "{hokkaido_name}就有{hokkaido}個",
        "image_main_value": "{hokkaido}個",
        "image_subtitle": "約占全國{hokkaido_pct}%",
        "image_footer": "寶可夢人孔蓋都道府縣排行榜",
        "map_pref": "北海道",
    },
    "installed-prefectures": {
        "type": "travel_trivia",
        "title": "已設置於{installed_count}個都道府縣",
        "stat": "{installed_count}個都道府縣",
        "main": "寶可夢人孔蓋已設置於{installed_count}個都道府縣。{empty_status}",
        "note": "雖然已經遍布日本各地，但仍有尚未設置的空白區域。",
        "share_title": "寶可夢人孔蓋已設置於{installed_count}個都道府縣。",
        "share_lead": "{empty_share_lead}",
        "share_body": "查看全國{total}個分布，就能發現還沒造訪過的地區。",
        "image_type": "summary_installed_prefectures",
        "image_title": "已設置寶可夢人孔蓋",
        "image_main_value": "{installed_count}個都道府縣",
        "image_subtitle": "{empty_image_subtitle}",
        "image_footer": "全國{total}個寶可夢人孔蓋一覽",
    },
    "tohoku": {
        "type": "regional_density",
        "title": "{tohoku_name}是{tohoku}個的密集區域",
        "stat": "{tohoku}個",
        "main": "{tohoku_name}地區有{tohoku}個寶可夢人孔蓋，是全國分布密度較高的區域之一。",
        "note": "福島縣、宮城縣、岩手縣等地都很值得安排巡訪。",
        "share_title": "{tohoku_name}地區有{tohoku}個寶可夢人孔蓋。",
        "share_lead": "福島、宮城、岩手等地，是很適合旅行巡訪的密集區域。",
        "share_body": "規劃東北旅行時，這個數字很有參考價值。",
        "image_type": "summary_regional_density",
        "image_title": "{tohoku_name}密集區域",
        "image_main_value": "{tohoku}個",
        "image_subtitle": "福島・宮城・岩手分布較多",
        "image_footer": "寶可夢人孔蓋地區分布",
    },
    "top-prefectures": {
        "type": "prefecture_rank",
        "title": "數量最多的前三名",
        "stat": "TOP3",
        "main": "寶可夢人孔蓋數量最多的前三名是：{top3}。",
        "note": "北日本地區在排行榜前段很有存在感。",
        "share_title": "寶可夢人孔蓋數量最多的都道府縣TOP3。",
        "share_lead": "{top3}位居前列。",
        "share_body": "把地圖換成數字來看，下一趟旅行的候選地會更清楚。",
        "image_type": "summary_top_prefectures",
        "image_title": "數量最多TOP3",
        "image_main_value": "TOP3",
        "image_subtitle": "{top3}",
        "image_footer": "寶可夢人孔蓋都道府縣排行榜",
        "map_label_key": "map_rank",
    },
    "fukushima": {
        "type": "prefecture_rank",
        "title": "{fukushima_name}位居全國第2",
        "stat": "{fukushima}個",
        "main": "{fukushima_name}有{fukushima}個寶可夢人孔蓋，僅次於北海道，位居全國第2。",
        "note": "只在縣內巡訪，也能是一趟內容很豐富的寶可夢人孔蓋之旅。",
        "share_title": "{fukushima_name}有{fukushima}個寶可夢人孔蓋。",
        "share_lead": "僅次於北海道，位居全國第2。",
        "share_body": "這個數量足以規劃一趟縣內巡訪。",
        "image_type": "summary_prefecture_rank",
        "image_title": "{fukushima_name}全國第2",
        "image_main_value": "{fukushima}個",
        "image_subtitle": "僅次於北海道",
        "image_footer": "寶可夢人孔蓋都道府縣排行榜",
        "map_pref": "福島県",
    },
    "miyagi-iwate": {
        "type": "regional_density",
        "title": "{miyagi_name}和{iwate_name}也很強",
        "stat": "{miyagi}+{iwate}個",
        "main": "{miyagi_name}有{miyagi}個，{iwate_name}有{iwate}個。東北是寶可夢人孔蓋巡訪的重要區域。",
        "note": "這些數字也很適合用來規劃東北旅行。",
        "share_title": "{miyagi_name}{miyagi}個，{iwate_name}{iwate}個。",
        "share_lead": "東北是寶可夢人孔蓋巡訪的強勢區域。",
        "share_body": "跨縣巡訪時，路線本身也會變成旅行的樂趣。",
        "image_type": "summary_regional_pair",
        "image_title": "{miyagi_name}和{iwate_name}",
        "image_main_value": "{miyagi}+{iwate}個",
        "image_subtitle": "東北旅行巡訪候選",
        "image_footer": "寶可夢人孔蓋地區分布",
        "map_pref": "宮城県",
    },
    "mie": {
        "type": "prefecture_rank",
        "title": "{mie_name}有{mie}個",
        "stat": "{mie}個",
        "main": "{mie_name}有{mie}個寶可夢人孔蓋，在近畿・東海區域也很有存在感。",
        "note": "很適合加入關西或東海方向的旅行路線。",
        "share_title": "{mie_name}有{mie}個寶可夢人孔蓋。",
        "share_lead": "在近畿・東海區域也很有存在感。",
        "share_body": "把它作為順路停靠點，旅行會多一點發現感。",
        "image_type": "summary_prefecture_rank",
        "image_title": "{mie_name}有{mie}個",
        "image_main_value": "{mie}個",
        "image_subtitle": "近畿・東海區域的注目縣",
        "image_footer": "寶可夢人孔蓋都道府縣排行榜",
        "map_pref": "三重県",
    },
    "empty-prefectures": {
        "type": "travel_trivia",
        "title": "仍沒有寶可夢人孔蓋的縣",
        "stat": "{empty_count}縣",
        "main": "{empty_names}仍然沒有寶可夢人孔蓋。",
        "note": "猜測下一處會設置在哪裡，也是樂趣之一。",
        "share_title": "仍沒有寶可夢人孔蓋的縣有{empty_count}個。",
        "share_lead": "分別是{empty_names}。",
        "share_body": "全國{total}個一覽能同時看到擴展範圍和空白區域。",
        "image_type": "summary_empty_prefectures",
        "image_title": "仍沒有寶可夢人孔蓋的縣",
        "image_main_value": "{empty_count}縣",
        "image_subtitle": "{empty_names}",
        "image_footer": "全國{total}個寶可夢人孔蓋一覽",
    },
}
FACT_COPY["ko"]["facts"] = {
    "hokkaido": {
        "type": "prefecture_rank",
        "title": "{hokkaido_name}에만 {hokkaido}개",
        "stat": "{hokkaido}개",
        "main": "{hokkaido_name}에는 포케후타가 {hokkaido}개 있습니다. 전국 {total}개 중 약 {hokkaido_pct}%입니다.",
        "note": "넓은 홋카이도에서는 포케후타 순회 자체가 하나의 여행이 됩니다.",
        "share_title": "{hokkaido_name}에만 포케후타가 {hokkaido}개.",
        "share_lead": "전국 {total}개 중 약 {hokkaido_pct}%입니다.",
        "share_body": "도도부현별 숫자를 보면 여행 후보지도 더 구체적으로 보입니다.",
        "image_type": "summary_prefecture_rank",
        "image_title": "{hokkaido_name}에만 {hokkaido}개",
        "image_main_value": "{hokkaido}개",
        "image_subtitle": "전국의 약 {hokkaido_pct}%",
        "image_footer": "포케후타 도도부현별 랭킹",
        "map_pref": "北海道",
    },
    "installed-prefectures": {
        "type": "travel_trivia",
        "title": "설치 완료는 {installed_count}개 도도부현",
        "stat": "{installed_count}개 도도부현",
        "main": "포케후타 설치 완료 지역은 {installed_count}개 도도부현입니다. {empty_status}",
        "note": "전국으로 퍼지고 있지만 아직 빈 지역도 남아 있습니다.",
        "share_title": "포케후타 설치 완료는 {installed_count}개 도도부현.",
        "share_lead": "{empty_share_lead}",
        "share_body": "전국 {total}개의 분포를 보면 아직 만나지 못한 지역도 보입니다.",
        "image_type": "summary_installed_prefectures",
        "image_title": "포케후타 설치 완료",
        "image_main_value": "{installed_count}개 도도부현",
        "image_subtitle": "{empty_image_subtitle}",
        "image_footer": "전국 {total}개 포케후타 일람",
    },
    "tohoku": {
        "type": "regional_density",
        "title": "{tohoku_name}는 {tohoku}개의 밀집 지역",
        "stat": "{tohoku}개",
        "main": "{tohoku_name} 지방에는 포케후타가 {tohoku}개 있습니다. 전국에서도 특히 밀도가 높은 지역입니다.",
        "note": "후쿠시마, 미야기, 이와테 등 순회할 만한 현이 이어집니다.",
        "share_title": "{tohoku_name} 지방에는 포케후타가 {tohoku}개.",
        "share_lead": "후쿠시마・미야기・이와테 등 여행하며 돌기 좋은 밀집 지역입니다.",
        "share_body": "도호쿠 여행지를 고를 때도 도움이 되는 숫자입니다.",
        "image_type": "summary_regional_density",
        "image_title": "{tohoku_name} 밀집 지역",
        "image_main_value": "{tohoku}개",
        "image_subtitle": "후쿠시마・미야기・이와테에 다수 분포",
        "image_footer": "지역별 포케후타 분포",
    },
    "top-prefectures": {
        "type": "prefecture_rank",
        "title": "많은 현 TOP3",
        "stat": "TOP3",
        "main": "포케후타가 많은 도도부현 TOP3는 {top3}입니다.",
        "note": "상위권에서는 북일본의 존재감이 큽니다.",
        "share_title": "포케후타가 많은 도도부현 TOP3.",
        "share_lead": "{top3}가 상위입니다.",
        "share_body": "숫자로 보면 다음 여행 후보지가 더 선명해집니다.",
        "image_type": "summary_top_prefectures",
        "image_title": "많은 현 TOP3",
        "image_main_value": "TOP3",
        "image_subtitle": "{top3}",
        "image_footer": "포케후타 도도부현별 랭킹",
        "map_label_key": "map_rank",
    },
    "fukushima": {
        "type": "prefecture_rank",
        "title": "{fukushima_name}는 전국 2위",
        "stat": "{fukushima}개",
        "main": "{fukushima_name}에는 포케후타가 {fukushima}개 있습니다. 홋카이도에 이어 전국 2위입니다.",
        "note": "현 안에서만 돌아도 충분히 진한 포케후타 여행이 됩니다.",
        "share_title": "{fukushima_name}에는 포케후타가 {fukushima}개.",
        "share_lead": "홋카이도에 이어 전국 2위입니다.",
        "share_body": "한 현 안에서도 충분한 순회 여행이 되는 수입니다.",
        "image_type": "summary_prefecture_rank",
        "image_title": "{fukushima_name} 전국 2위",
        "image_main_value": "{fukushima}개",
        "image_subtitle": "홋카이도 다음으로 많은 설치 수",
        "image_footer": "포케후타 도도부현별 랭킹",
        "map_pref": "福島県",
    },
    "miyagi-iwate": {
        "type": "regional_density",
        "title": "{miyagi_name}와 {iwate_name}도 강세",
        "stat": "{miyagi}+{iwate}개",
        "main": "{miyagi_name}에는 {miyagi}개, {iwate_name}에는 {iwate}개. 도호쿠는 포케후타 순회의 유력 지역입니다.",
        "note": "도호쿠 여행 목적지를 고를 때도 쓰기 좋은 숫자입니다.",
        "share_title": "{miyagi_name} {miyagi}개, {iwate_name} {iwate}개.",
        "share_lead": "도호쿠는 포케후타 순회의 유력 지역입니다.",
        "share_body": "현을 넘나들며 돌면 경로 자체가 여행의 재미가 됩니다.",
        "image_type": "summary_regional_pair",
        "image_title": "{miyagi_name}와 {iwate_name}",
        "image_main_value": "{miyagi}+{iwate}개",
        "image_subtitle": "도호쿠 여행 순회 후보",
        "image_footer": "지역별 포케후타 분포",
        "map_pref": "宮城県",
    },
    "mie": {
        "type": "prefecture_rank",
        "title": "{mie_name}는 {mie}개",
        "stat": "{mie}개",
        "main": "{mie_name}에는 포케후타가 {mie}개 있습니다. 긴키・도카이 지역에서도 존재감이 있습니다.",
        "note": "간사이・도카이 방면 여행 일정에도 넣기 좋은 지역입니다.",
        "share_title": "{mie_name}에는 포케후타가 {mie}개.",
        "share_lead": "긴키・도카이 지역에서도 존재감 있는 설치 수입니다.",
        "share_body": "이동 경로에 더하면 작은 발견이 있는 여행이 됩니다.",
        "image_type": "summary_prefecture_rank",
        "image_title": "{mie_name}는 {mie}개",
        "image_main_value": "{mie}개",
        "image_subtitle": "긴키・도카이 지역의 주목 현",
        "image_footer": "포케후타 도도부현별 랭킹",
        "map_pref": "三重県",
    },
    "empty-prefectures": {
        "type": "travel_trivia",
        "title": "아직 포케후타가 없는 현",
        "stat": "{empty_count}개 현",
        "main": "{empty_names}에는 아직 포케후타가 없습니다.",
        "note": "다음에는 어디로 확장될지 예상하는 재미도 있습니다.",
        "share_title": "아직 포케후타가 없는 현은 {empty_count}곳.",
        "share_lead": "{empty_names}입니다.",
        "share_body": "전국 {total}개의 일람을 보면 확산 지역과 빈 지역이 함께 보입니다.",
        "image_type": "summary_empty_prefectures",
        "image_title": "아직 포케후타가 없는 현",
        "image_main_value": "{empty_count}개 현",
        "image_subtitle": "{empty_names}",
        "image_footer": "전국 {total}개 포케후타 일람",
    },
}


def _localized_fact_copy(lang: str) -> dict:
    return FACT_COPY.get(lang, FACT_COPY["en"])


def _build_facts(s: dict, stats: dict, tr) -> list[dict]:
    lang = s.get("html_lang", "en")
    copy = _localized_fact_copy(lang)
    counts = {item["pref"]: item["count"] for item in stats["by_pref"]}
    total = stats["total"]
    hokkaido = counts.get("北海道", 0)
    fukushima = counts.get("福島県", 0)
    miyagi = counts.get("宮城県", 0)
    iwate = counts.get("岩手県", 0)
    mie = counts.get("三重県", 0)
    tohoku = stats["regional"].get("東北", 0)
    installed_count = len(stats["installed"])
    empty_count = len(stats["empty"])
    hokkaido_pct = round((hokkaido / total) * 100) if total else 0
    top3 = copy["top3_separator"].join(
        tr(item["pref"]) for item in stats["ranking"][:3]
    )
    empty_names = copy["list_separator"].join(
        tr(item["pref"]) for item in stats["empty"]
    )
    if empty_count:
        empty_status = copy["empty_status"].format(empty_count=empty_count)
        empty_share_lead = copy["empty_share_lead"].format(empty_count=empty_count)
        empty_image_subtitle = copy["empty_image_subtitle"].format(
            empty_count=empty_count
        )
    else:
        empty_status = copy["all_installed_status"]
        empty_share_lead = copy["all_installed_share_lead"]
        empty_image_subtitle = copy["all_installed_image_subtitle"]
    region_names = s.get("region_names", {})
    ctx = {
        "total": total,
        "hokkaido": hokkaido,
        "hokkaido_pct": hokkaido_pct,
        "hokkaido_name": tr("北海道"),
        "fukushima": fukushima,
        "fukushima_name": tr("福島県"),
        "miyagi": miyagi,
        "miyagi_name": tr("宮城県"),
        "iwate": iwate,
        "iwate_name": tr("岩手県"),
        "mie": mie,
        "mie_name": tr("三重県"),
        "tohoku": tohoku,
        "tohoku_name": region_names.get("東北", "Tohoku"),
        "installed_count": installed_count,
        "empty_count": empty_count,
        "empty_names": empty_names,
        "empty_status": empty_status,
        "empty_share_lead": empty_share_lead,
        "empty_image_subtitle": empty_image_subtitle,
        "top3": top3,
    }

    facts = []
    for fact_id, template in copy["facts"].items():
        if fact_id == "empty-prefectures" and not empty_count:
            continue
        fact = {
            "id": fact_id,
            "type": template["type"],
            "share_url": s["canonical"],
            "hashtags": copy["hashtags"],
            "map_href": _map_href(s["map_base_href"], template.get("map_pref")),
            "map_label": (
                copy[template.get("map_label_key", "map_all")]
                if "map_pref" not in template
                else copy["map_pref"].format(pref=tr(template["map_pref"]))
            ),
        }
        for key in (
            "title", "stat", "main", "note",
            "share_title", "share_lead", "share_body",
            "image_type", "image_title", "image_main_value",
            "image_subtitle", "image_footer",
        ):
            fact[key] = template[key].format(**ctx)
        facts.append(fact)
    return facts


def _fact_share_text(fact: dict) -> str:
    lines = [
        fact["share_title"],
        fact["share_lead"],
        fact["share_body"],
        " ".join(fact["hashtags"]),
    ]
    return "\n".join(line for line in lines if line)


def _build_fact_sections(s: dict, stats: dict, tr) -> tuple[str, str]:
    copy = _localized_fact_copy(s.get("html_lang", "en"))
    facts = _build_facts(s, stats, tr)
    if not facts:
        return "", ""
    daily_fact = facts[0]

    def action_links(fact: dict) -> str:
        share_href = _twitter_intent_url(_fact_share_text(fact), fact["share_url"])
        map_href = fact["map_href"]
        return (
            '<div class="summary-actions">'
            f'<a class="summary-action" href="{escape(share_href)}" '
            'target="_blank" rel="noopener noreferrer" '
            f'{_track_attrs("summary_share_x_click", fact, fact["share_url"])}>'
            f'{escape(copy["share"])}</a>'
            f'<a class="summary-action secondary" href="{escape(map_href)}" '
            f'{_track_attrs("summary_map_click", fact, map_href)}>'
            f'{escape(fact["map_label"])}</a>'
            '</div>'
        )

    daily_html = (
        f'\n    <section class="daily-fact-card" aria-labelledby="daily-fact-heading" '
        f'data-fact-id="{escape(daily_fact["id"])}" '
        f'data-fact-title="{escape(daily_fact["title"])}" '
        f'data-image-type="{escape(daily_fact["image_type"])}" '
        f'data-image-title="{escape(daily_fact["image_title"])}" '
        f'data-image-main-value="{escape(daily_fact["image_main_value"])}" '
        f'data-image-subtitle="{escape(daily_fact["image_subtitle"])}" '
        f'data-image-footer="{escape(daily_fact["image_footer"])}">'
        f'\n      <span class="daily-fact-label">{escape(copy["daily"])}</span>'
        f'\n      <h2 id="daily-fact-heading"><strong>{escape(daily_fact["main"])}</strong></h2>'
        f'\n      <p>{escape(daily_fact["note"])}</p>'
        f'\n      {action_links(daily_fact)}'
        f'\n    </section>\n'
    )

    card_items = "\n        ".join(
        f'<li>'
        f'<article class="summary-fact-card" data-fact-id="{escape(fact["id"])}" '
        f'data-fact-title="{escape(fact["title"])}" '
        f'data-image-type="{escape(fact["image_type"])}" '
        f'data-image-title="{escape(fact["image_title"])}" '
        f'data-image-main-value="{escape(fact["image_main_value"])}" '
        f'data-image-subtitle="{escape(fact["image_subtitle"])}" '
        f'data-image-footer="{escape(fact["image_footer"])}">'
        f'<span class="summary-fact-number">{escape(fact["stat"])}</span>'
        f'<h3>{escape(fact["title"])}</h3>'
        f'<p class="summary-fact-main">{escape(fact["main"])}</p>'
        f'<p class="summary-fact-note">{escape(fact["note"])}</p>'
        f'{action_links(fact)}'
        f'</article>'
        f'</li>'
        for fact in facts
    )
    list_html = (
        f'\n    <section class="summary-section" aria-labelledby="fact-list-heading">'
        f'\n      <h2 id="fact-list-heading">{escape(copy["section"])}</h2>'
        f'\n      <ul class="fact-card-grid">\n        {card_items}\n      </ul>'
        f'\n    </section>\n'
    )

    return daily_html, list_html


def _build_tracking_script(s: dict) -> str:
    return """\
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-K18NR4GZG2"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
    gtag('js', new Date());
    gtag('config', 'G-K18NR4GZG2', {
      'anonymize_ip': true,
      'page_path': window.location.pathname
    });

    document.addEventListener('click', function (event) {
      if (!window.gtag) return;

      const target = event.target.closest('[data-summary-event]');
      const card = event.target.closest('.daily-fact-card[data-fact-id], .summary-fact-card[data-fact-id]');
      if (card && !target) {
        window.gtag('event', 'summary_fact_card_click', {
          fact_id: card.dataset.factId || '',
          fact_title: card.dataset.factTitle || '',
          image_type: card.dataset.imageType || '',
          target_url: window.location.href
        });
      }

      if (!target) return;
      window.gtag('event', target.dataset.summaryEvent, {
        fact_id: target.dataset.factId || '',
        fact_title: target.dataset.factTitle || '',
        image_type: target.dataset.imageType || '',
        target_url: target.dataset.targetUrl || target.href || ''
      });
    });
  </script>
"""


def _build_regional_section(s: dict, stats: dict) -> str:
    regional = stats["regional"]
    region_names = s["region_names"]
    sorted_regions = sorted(regional.items(), key=lambda x: -x[1])
    if not sorted_regions:
        return ""

    r1name_ja, r1count = sorted_regions[0]
    r1display = region_names.get(r1name_ja, r1name_ja)

    if len(sorted_regions) >= 2:
        r2name_ja, r2count = sorted_regions[1]
        r2display = region_names.get(r2name_ja, r2name_ja)
        text = s["regional_top2"].format(
            r1name=r1display, r1count=r1count,
            r2name=r2display, r2count=r2count,
        )
    else:
        text = s["regional_top1"].format(r1name=r1display, r1count=r1count)
    text += " " + s["regional_outro"]

    h2 = escape(s["h2_regional"])
    return (
        f'\n    <section class="summary-section" aria-labelledby="regional-trend-heading">'
        f'\n      <h2 id="regional-trend-heading">{h2}</h2>'
        f'\n      <div class="regional-trend-box"><p>{escape(text)}</p></div>'
        f'\n    </section>\n'
    )


_FORM_PREFIX: dict[str, str] = {
    "alola": "アローラ",
    "galar": "ガラル",
    "hisui": "ヒスイ",
    "paldea": "パルデア",
}


def _normalize_katakana(text: str) -> str:
    """Convert hiragana to katakana for loose matching (e.g. ゴンべ → ゴンベ)."""
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in text)


def load_pokemon_metadata_with_slugs(path: Path) -> dict[str, dict]:
    """Load docs/pokemon_metadata.json (has slug field) indexed by ja name.

    Mirrors the lookup logic in generate_pokemon_pages.load_pokemon_metadata:
    - Base form wins over regional variants for the bare ja_name key.
    - Regional prefix variants (e.g. "アローラロコン") are added as extra keys.
    - Katakana normalization handles hiragana/katakana mismatches (e.g. ゴンべ).
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    result: dict[str, dict] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        ja_name = entry.get("names", {}).get("ja", "")
        slug = entry.get("slug", "")
        form = entry.get("form") or ""
        if not ja_name or not slug:
            continue
        # Base form (form is empty/null) always wins for the bare ja_name key.
        if ja_name not in result or not form:
            result[ja_name] = entry
        # Add prefixed key for regional forms (e.g. "アローラロコン").
        prefix = _FORM_PREFIX.get(form, "")
        if prefix:
            combined = prefix + ja_name
            if combined not in result:
                result[combined] = entry
    # Katakana normalization: cover hiragana/katakana mismatches in ndjson data.
    for key in list(result.keys()):
        normalized = _normalize_katakana(key)
        if normalized != key and normalized not in result:
            result[normalized] = result[key]
    return result


def load_photos(path: Path) -> dict:
    """Load latest-manhole-photos.json."""
    if not path.exists():
        return {"photos": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"photos": {}}


def build_pokemon_stats(records: list[dict], pokemon_metadata: dict) -> dict:
    """Return pokemon stats: by_count and by_city_count sorted desc."""
    manhole_counts: dict[str, int] = {}
    city_sets: dict[str, set] = {}

    for record in records:
        if record.get("status") != "active":
            continue
        pref = record.get("prefecture", "")
        city = record.get("city", "")
        city_key = f"{pref}/{city}"
        for poke_ja in record.get("pokemons", []):
            manhole_counts[poke_ja] = manhole_counts.get(poke_ja, 0) + 1
            city_sets.setdefault(poke_ja, set()).add(city_key)

    entries = []
    for ja_name, count in manhole_counts.items():
        meta = pokemon_metadata.get(ja_name)
        if not meta:
            continue
        slug = meta.get("slug", "")
        if not slug:
            continue
        entries.append({
            "ja_name": ja_name,
            "slug": slug,
            "count": count,
            "city_count": len(city_sets.get(ja_name, set())),
        })

    by_count = sorted(entries, key=lambda x: (-x["count"], x["ja_name"]))
    by_city_count = sorted(entries, key=lambda x: (-x["city_count"], x["ja_name"]))
    return {"by_count": by_count, "by_city_count": by_city_count}


def _pokemon_lp_url(map_base: str, slug: str) -> str:
    return escape(f"{map_base}pokemon/{quote(slug)}/")


def _build_search_hub_section(s: dict) -> str:
    hub = s.get("search_hub")
    if not hub:
        return ""
    map_base = s["map_base_href"]
    cards = [
        (hub["card_pref_title"], hub["card_pref_desc"], "#prefecture-count-heading"),
        (hub["card_pokemon_title"], hub["card_pokemon_desc"], f"{map_base}pokemon/"),
        (hub["card_map_title"], hub["card_map_desc"], s["nav_home_href"]),
    ]
    cards_html = "\n".join(
        f'<a class="search-hub-card" href="{escape(href)}">'
        f'<strong>{escape(title)}</strong>'
        f'<span>{escape(desc)}</span>'
        f'</a>'
        for title, desc, href in cards
    )
    h2 = escape(hub["h2"])
    return (
        f'\n    <section class="summary-section" aria-labelledby="search-hub-heading">'
        f'\n      <h2 id="search-hub-heading">{h2}</h2>'
        f'\n      <div class="search-hub-grid">\n{cards_html}\n      </div>'
        f'\n    </section>\n'
    )


def _build_popular_pokemon_section(s: dict, pokemon_stats: dict) -> str:
    if not pokemon_stats.get("by_count"):
        return ""
    poke_s = s.get("popular_pokemon")
    if not poke_s:
        return ""
    map_base = s["map_base_href"]
    count_unit = s["count_unit"]
    top = pokemon_stats["by_count"][:12]

    cards_html = "\n".join(
        f'<a class="pokemon-card" href="{_pokemon_lp_url(map_base, p["slug"])}">'
        f'<strong>{escape(p["ja_name"])}</strong>'
        f'<span>{p["count"]}{escape(count_unit)}</span>'
        f'</a>'
        for p in top
    )
    h2 = escape(poke_s["h2"])
    return (
        f'\n    <section class="summary-section" aria-labelledby="popular-pokemon-heading">'
        f'\n      <h2 id="popular-pokemon-heading">{h2}</h2>'
        f'\n      <div class="pokemon-popular-grid">\n{cards_html}\n      </div>'
        f'\n    </section>\n'
    )


def _build_latest_photos_section(
    s: dict, records_by_id: dict, photos_data: dict
) -> str:
    if s.get("pref_key") != "ja":
        return ""
    photos_s = s.get("latest_photos")
    if not photos_s:
        return ""
    photos = photos_data.get("photos", {})
    if not photos:
        return ""

    sorted_photos = sorted(
        photos.values(),
        key=lambda p: p.get("created_at", ""),
        reverse=True,
    )[:6]

    cards = []
    for photo in sorted_photos:
        mid = str(photo.get("manhole_id", ""))
        record = records_by_id.get(mid, {})
        pref = record.get("prefecture", "")
        city = record.get("city", "")
        title = record.get("title", "")
        pokemons = "・".join(record.get("pokemons", [])[:2])
        location = f"{pref}{city}" if pref and city else title
        local_image = IMAGE_DIR / f"{mid}_latest.jpeg"
        url = (
            f"{BASE_URL}/manhole/image/{quote(mid, safe='')}_latest.jpeg"
            if mid and local_image.exists()
            else photo.get("url") or ""
        )
        date = (photo.get("created_at") or "")[:10]
        manhole_href = f"/manholes/{mid}/"
        display_title = pokemons or title
        if not url:
            continue
        cards.append(
            f'<a class="photo-card" href="{escape(manhole_href)}">'
            f'<img src="{escape(url)}" alt="{escape(display_title)}" loading="lazy" decoding="async">'
            f'<span class="photo-card-title">{escape(display_title)}</span>'
            f'<span class="photo-card-meta">{escape(location)} · {escape(date)}</span>'
            f'</a>'
        )

    if not cards:
        return ""

    h2 = escape(photos_s["h2"])
    note = escape(photos_s["note"])
    return (
        f'\n    <section class="summary-section" aria-labelledby="latest-photos-heading">'
        f'\n      <h2 id="latest-photos-heading">{h2}</h2>'
        f'\n      <p class="section-note">{note}</p>'
        f'\n      <div class="photos-grid">\n{"".join(cards)}\n      </div>'
        f'\n    </section>\n'
    )


def _build_no_photos_section(
    s: dict, records_by_id: dict, photos_data: dict
) -> str:
    if s.get("pref_key") != "ja":
        return ""
    np_s = s.get("no_photos")
    if not np_s:
        return ""
    photo_ids = set(str(k) for k in photos_data.get("photos", {}).keys())
    no_photo = [
        r for r in records_by_id.values()
        if r.get("status") == "active" and str(r.get("id", "")) not in photo_ids
    ]
    if not no_photo:
        return ""

    by_pref: dict[str, int] = {}
    for r in no_photo:
        pref = r.get("prefecture", "その他")
        by_pref[pref] = by_pref.get(pref, 0) + 1

    total = len(no_photo)
    top_prefs = sorted(by_pref.items(), key=lambda x: -x[1])[:8]
    pref_items = "\n".join(
        f'<li class="summary-list-item">'
        f'<a class="summary-link" href="{escape(f"/?pref={quote(pref)}")}">{escape(pref)}</a>'
        f'<small>{count}枚</small>'
        f'</li>'
        for pref, count in top_prefs
    )
    h2 = escape(np_s["h2"])
    total_text = escape(np_s["total"].format(count=total))
    cta = escape(np_s["cta"])
    return (
        f'\n    <section class="summary-section" aria-labelledby="no-photos-heading">'
        f'\n      <h2 id="no-photos-heading">{h2}</h2>'
        f'\n      <p class="section-note">{total_text}。{cta}</p>'
        f'\n      <ul class="summary-list" style="margin-top:12px;">{pref_items}</ul>'
        f'\n    </section>\n'
    )


def _build_pokemon_ranking_section(s: dict, pokemon_stats: dict) -> str:
    if not pokemon_stats:
        return ""
    pk_s = s.get("pokemon_ranking")
    if not pk_s:
        return ""
    map_base = s["map_base_href"]
    count_unit = s["count_unit"]
    pref_unit = pk_s.get("pref_count_unit", "")

    def rank_items(entries: list[dict], value_key: str, unit: str) -> str:
        return "\n".join(
            f'<li>'
            f'<a class="summary-link" href="{_pokemon_lp_url(map_base, p["slug"])}">'
            f'{escape(p["ja_name"])}</a>'
            f'<small>{p[value_key]}{escape(unit)}</small>'
            f'</li>'
            for p in entries[:10]
        )

    count_items = rank_items(pokemon_stats["by_count"], "count", count_unit)
    city_items = rank_items(pokemon_stats["by_city_count"], "city_count", pref_unit)

    h2 = escape(pk_s["h2"])
    h3_count = escape(pk_s["h3_count"])
    h3_pref = escape(pk_s["h3_pref"])
    return (
        f'\n    <section class="summary-section" aria-labelledby="pokemon-ranking-heading">'
        f'\n      <h2 id="pokemon-ranking-heading">{h2}</h2>'
        f'\n      <div class="pokemon-ranking-cols">'
        f'\n        <div><h3>{h3_count}</h3>'
        f'<ol class="summary-list">{count_items}</ol></div>'
        f'\n        <div><h3>{h3_pref}</h3>'
        f'<ol class="summary-list">{city_items}</ol></div>'
        f'\n      </div>'
        f'\n    </section>\n'
    )


def render_page(s: dict, stats: dict, pref_names: dict, pokemon_stats: dict, records_by_id: dict, photos_data: dict) -> str:
    pref_key = s["pref_key"]

    def tr(ja_name: str) -> str:
        if pref_key == "ja":
            return ja_name
        return pref_names.get(ja_name, {}).get(pref_key, ja_name)

    total = stats["total"]
    installed = stats["installed"]
    empty = stats["empty"]
    ranking = stats["ranking"]
    count_unit = s["count_unit"]
    map_base = s["map_base_href"]

    ai_html = _build_ai_summary(s, stats, tr)
    discovery_html = _build_discovery_section(s, stats, tr)
    daily_fact_html, fact_list_html = _build_fact_sections(s, stats, tr)
    regional_html = _build_regional_section(s, stats)
    tracking_script = _build_tracking_script(s)
    search_hub_html = _build_search_hub_section(s)
    popular_pokemon_html = _build_popular_pokemon_section(s, pokemon_stats)
    latest_photos_html = _build_latest_photos_section(s, records_by_id, photos_data)
    no_photos_html = _build_no_photos_section(s, records_by_id, photos_data)
    pokemon_ranking_html = _build_pokemon_ranking_section(s, pokemon_stats)

    def map_link(pref_ja: str) -> str:
        href = f'{map_base}?pref={quote(pref_ja)}'
        return f'<a class="summary-link" href="{escape(href)}">{escape(s["map_link_text"])}</a>'

    table_rows = "\n            ".join(
        f"<tr>"
        f"<td>{escape(tr(item['pref']))}</td>"
        f"<td>{item['count']}{escape(count_unit)}</td>"
        f"<td>{map_link(item['pref']) if item['count'] > 0 else escape(s['table_no_map'])}</td>"
        f"</tr>"
        for item in stats["by_pref"]
    )

    ranking_items = "\n        ".join(
        f"<li>"
        f"{escape(tr(item['pref']))}"
        f"<small>{item['count']}{escape(count_unit)}</small>"
        f"{map_link(item['pref'])}"
        f"</li>"
        for item in ranking
    )

    if empty:
        empty_items = "\n        ".join(
            f"<li>{escape(tr(item['pref']))}</li>"
            for item in empty
        )
    else:
        empty_items = f'<li class="summary-empty">{escape(s["no_empty"])}</li>'

    pt = escape(s["page_title"])
    md = escape(_format_summary_text(s["meta_desc"], s, stats))
    subtitle = escape(_format_summary_text(s["subtitle"], s, stats))
    can = escape(s["canonical"])

    return f"""<!doctype html>
<html lang="{s['html_lang']}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{pt}</title>
  <meta name="description" content="{md}">
  <meta name="robots" content="index,follow">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="{s['og_locale']}">
  <meta property="og:title" content="{pt}">
  <meta property="og:description" content="{md}">
  <meta property="og:url" content="{can}">
  <meta property="og:image" content="{OGP_IMAGE}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{pt}">
  <meta name="twitter:description" content="{md}">
  <meta name="twitter:image" content="{OGP_IMAGE}">
  <link rel="canonical" href="{can}">
{_HREFLANG}
  <link rel="icon" href="https://data.pokefuta.com/assets/pokefuta-marker.svg" type="image/svg+xml">
  <style>
{_CSS}
  </style>
</head>
<body>
  <main class="summary-page">
    <nav class="summary-hero" aria-label="{escape(s['breadcrumb_aria'])}">
      <a href="{escape(s['nav_home_href'])}">{escape(s['nav_home_text'])}</a>
      <h1>{escape(s['h1'])}</h1>
      <p>{subtitle}</p>
    </nav>
    {search_hub_html}
    {daily_fact_html}
    {ai_html}
    <section class="summary-stats" aria-label="{escape(s['stats_aria'])}">
      <div class="summary-stat">
        <span>{escape(s['stat_total'])}</span>
        <strong>{escape(s['total_fmt'].format(count=total))}</strong>
      </div>
      <div class="summary-stat">
        <span>{escape(s['stat_installed'])}</span>
        <strong>{escape(s['installed_fmt'].format(count=len(installed)))}</strong>
      </div>
      <div class="summary-stat">
        <span>{escape(s['stat_empty'])}</span>
        <strong>{escape(s['empty_fmt'].format(count=len(empty)))}</strong>
      </div>
    </section>
    {popular_pokemon_html}
    {latest_photos_html}
    {no_photos_html}
    {fact_list_html}
    {discovery_html}
    <section class="summary-section" aria-labelledby="prefecture-count-heading">
      <h2 id="prefecture-count-heading">{escape(s['h2_pref_count'])}</h2>
      <div class="summary-table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">{escape(s['th_pref'])}</th>
              <th scope="col">{escape(s['th_count'])}</th>
              <th scope="col">{escape(s['th_map'])}</th>
            </tr>
          </thead>
          <tbody>
            {table_rows}
          </tbody>
        </table>
      </div>
    </section>

    <section class="summary-section" aria-labelledby="ranking-heading">
      <h2 id="ranking-heading">{escape(s['h2_ranking'])}</h2>
      <ol class="summary-list">
        {ranking_items}
      </ol>
      <p style="margin-top:10px;font-size:.875rem;color:#574b41;">{s['ranking_note']}</p>
    </section>
    {pokemon_ranking_html}
    {regional_html}
    <section class="summary-section" aria-labelledby="empty-prefecture-heading">
      <h2 id="empty-prefecture-heading">{escape(s['h2_empty'])}</h2>
      <p class="empty-note">{escape(s['empty_note'])}</p>
      <ul class="summary-list" style="margin-top:10px;">
        {empty_items}
      </ul>
    </section>

    <section class="summary-section" aria-labelledby="map-link-heading">
      <h2 id="map-link-heading">{escape(s['h2_map'])}</h2>
      <p>{escape(s['map_desc'])}</p>
      <a class="summary-cta" href="{escape(s['nav_home_href'])}">{escape(s['cta_text'])}</a>
    </section>
  </main>
{tracking_script}
</body>
</html>"""


def main() -> None:
    if not NDJSON.exists():
        print(f"[ERROR] Not found: {NDJSON}", file=sys.stderr)
        sys.exit(1)

    pref_names: dict = {}
    if PREFECTURES_JSON.exists():
        pref_names = json.loads(PREFECTURES_JSON.read_text(encoding="utf-8"))

    records = load_records(NDJSON)
    stats = build_stats(records)
    print(f"[INFO] {stats['total']} manholes across {len(stats['installed'])} prefectures")

    pokemon_metadata = load_pokemon_metadata_with_slugs(POKEMON_METADATA_JSON)
    photos_data = load_photos(PHOTOS_JSON)
    pokemon_stats = build_pokemon_stats(records, pokemon_metadata)
    records_by_id = {str(r.get("id", "")): r for r in records}
    print(f"[INFO] {len(pokemon_stats['by_count'])} pokemon with slugs, {len(photos_data.get('photos', {}))} photos")

    for lang, s in SUMMARY_STRINGS.items():
        html = render_page(s, stats, pref_names, pokemon_stats, records_by_id, photos_data)
        out = DIST / s["out_path"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"[OK]  dist/{s['out_path']} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
