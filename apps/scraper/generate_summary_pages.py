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
        "page_title": "ポケふたは全国に何個ある？都道府県別の数・多い県ランキング",
        "meta_desc": "全国のポケふた・ポケモンマンホールの総数、都道府県別の設置数、多い県、まだ設置されていない県をまとめています。",
        "breadcrumb_aria": "パンくず",
        "nav_home_text": "全国マップ",
        "nav_home_href": "/",
        "h1": "ポケふたは全国に何個ある？",
        "subtitle": "全国のポケふた・ポケモンマンホールを、既存データから都道府県別に集計しています。",
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
        "h2_ranking": "ポケふたが多い県ランキング",
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
        "regional_top2": "地方別では{r1name}（{r1count}枚）が最も多く、次いで{r2name}（{r2count}枚）となっています。",
        "regional_top1": "地方別では{r1name}（{r1count}枚）が最も多くなっています。",
        "regional_outro": "ポケふたは地方自治体・観光協会との連携で設置されることが多く、観光地や駅周辺に置かれているケースが目立ちます。地域を旅しながら複数のポケふたを巡るルートを作るのも人気の楽しみ方です。",
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


def render_page(s: dict, stats: dict, pref_names: dict) -> str:
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
    regional_html = _build_regional_section(s, stats)

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
    md = escape(s["meta_desc"])
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
      <p>{escape(s['subtitle'])}</p>
    </nav>

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

    for lang, s in SUMMARY_STRINGS.items():
        html = render_page(s, stats, pref_names)
        out = DIST / s["out_path"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"[OK]  dist/{s['out_path']} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
