"""多言語トップ（/en/・/zh-TW/・/zh-CN/・/ko/）の文言。

generate_top_page_en.py が使う。テーマ名・イベントの見出しなど、地図ページと共通の語は
apps/web/i18n/strings.<lang>.json にあるのでそちらを使い、ここにはトップだけの文を置く。

呼び方は公式サイトに合わせる: Poké Lids / 寶可夢人孔蓋 / 宝可梦井盖 / 포켓몬 맨홀。
{…} は str.format の差し込み。
"""

from __future__ import annotations

TEXT: dict[str, dict[str, object]] = {
    "en": {
        "html_lang": "en",
        "og_locale": "en_US",
        "page_title": "Poké Lids Directory — Every Pokémon Manhole in Japan",
        "keywords": "Poké Lids,Pokefuta,Pokémon manhole,Japan,travel,map,prefecture",
        "site_name": "Pokéfuta Directory",
        "lid": "Poké Lid",
        "sep": ", ",
        "description": (
            "Find all {total} Poké Lids (Pokéfuta, Pokémon manhole covers) across "
            "{prefs} prefectures in Japan — with fan photos, a map, "
            "a prefecture list and a Pokémon index to plan your trip."
        ),
        "short_description": "{total} Poké Lids (Pokémon manhole covers) in {prefs} prefectures of Japan, with fan photos and a map.",
        "ld_map": "Poké Lids map",
        "ld_pokemon": "Poké Lids by Pokémon",
        "ld_stats": "Poké Lids statistics",
        "ld_prefs": "Prefectures with Poké Lids",
        "ld_pref_item": "Poké Lids in {pref} ({count})",
        "stat_lids": "Poké Lids",
        "stat_prefs": "Prefectures",
        "stat_pokemon": "Pokémon",
        "stat_photos": "Fan photos",
        "quick_map": "Search the map",
        "quick_pref": "By prefecture",
        "quick_pokemon": "By Pokémon",
        "quick_theme": "By theme",
        "quick_aria": "Main ways to search",
        "lead": (
            "Poké Lids (<i>Pokéfuta</i>) are Pokémon-themed manhole covers. "
            "{total} of them are installed in {prefs} of Japan's 47 prefectures, "
            "from Hokkaido to Okinawa. This directory collects every location, the Pokémon on each lid "
            "and photos taken by fans"
        ),
        "lead_popular": " — <b>{names}</b> and {npoke} Pokémon in all.",
        "lead_end": ".",
        "mosaic_note": "Latest fan photos (updated {date})",
        "map_pin_title": "{pref}: {count} Poké Lids — view on the map",
        "map_aria": "Map of Poké Lids by prefecture",
        "map_cta": "🗺 Open the full-screen map",
        "eyebrow": "POKÉMON MANHOLE DIRECTORY",
        "h1": "Explore all {total} Poké Lids in Japan by map and list",
        "ways_title": "Choose how to search",
        "way_map_title": "Map & your location",
        "way_map_text": "See every spot on a map of Japan and find the Poké Lids closest to you.",
        "way_map_open": "Open the map",
        "way_map_theme": "Filter by theme",
        "way_pref_title": "By prefecture",
        "way_pref_text": "Browse the {prefs} prefectures with Poké Lids, grouped by region.",
        "way_pokemon_title": "By Pokémon",
        "way_pokemon_text": "Look up your favourite among {npoke} Pokémon featured on the lids.",
        "way_theme_title": "By theme",
        "way_theme_text": "Roadside stations, World Heritage sites, remote islands and more.",
        "new_title": "New Poké Lids",
        "new_small": "{n} in the last {days} days",
        "photos_title": "Latest fan photos",
        "photos_cta": "Post your photo on Pokéfuta Album",
        "photos_empty": "No photos yet. Be the first to post one.",
        "photos_lead": "Recent posts, picked region by region from north to south so no single area dominates.",
        "photos_coverage": " Fans have photographed {n} locations so far.",
        "alt_photo": "Fan photo of the Poké Lid in {where} ({names})",
        "alt_photo_noname": "Fan photo of a Poké Lid in {where}",
        "alt_poke": "{name} Poké Lid in {pref}",
        "events_note": "Event names and details are in Japanese.",
        "events_show_all": "Show all ({n})",
        "pref_text": (
            "Poké Lids are installed in {prefs} of Japan's 47 prefectures. "
            "They are listed by region from north to south, with the number of lids in each."
        ),
        "pref_none": "As of {month}, there are no Poké Lids in {places}.",
        "pref_more": "All 47 prefectures",
        "poke_count": "{n} lids",
        "poke_all": "All Pokémon",
        "purpose_title": "Search by purpose",
        "purpose_theme": "By theme",
        "purpose_theme_more": "Explore on the map",
        "purpose_pokemon": "Most common Pokémon",
        "regions": {
            "北海道・東北": "Hokkaido & Tohoku", "関東": "Kanto", "中部": "Chubu", "近畿": "Kinki",
            "中国": "Chugoku", "四国": "Shikoku", "九州・沖縄": "Kyushu & Okinawa",
        },
    },
    "zh-TW": {
        "html_lang": "zh-TW",
        "og_locale": "zh_TW",
        "page_title": "寶可夢人孔蓋圖鑑｜日本全國寶可夢人孔蓋（Pokéfuta）一覽・地圖",
        "keywords": "寶可夢人孔蓋,Pokéfuta,Poké Lids,日本,地圖,旅遊,都道府縣",
        "site_name": "寶可夢人孔蓋圖鑑",
        "lid": "寶可夢人孔蓋",
        "sep": "、",
        "description": (
            "日本{prefs}個都道府縣共{total}個寶可夢人孔蓋（Pokéfuta）全收錄。"
            "附粉絲拍攝的照片、地圖、都道府縣一覽與寶可夢索引，規劃旅程好幫手。"
        ),
        "short_description": "日本{prefs}個都道府縣共{total}個寶可夢人孔蓋，附粉絲照片與地圖。",
        "ld_map": "寶可夢人孔蓋地圖",
        "ld_pokemon": "依寶可夢查看寶可夢人孔蓋",
        "ld_stats": "寶可夢人孔蓋統計",
        "ld_prefs": "設有寶可夢人孔蓋的都道府縣",
        "ld_pref_item": "{pref}的寶可夢人孔蓋（{count}個）",
        "stat_lids": "個人孔蓋",
        "stat_prefs": "個都道府縣",
        "stat_pokemon": "種寶可夢",
        "stat_photos": "張粉絲照片",
        "quick_map": "用地圖尋找",
        "quick_pref": "依都道府縣",
        "quick_pokemon": "依寶可夢",
        "quick_theme": "依主題",
        "quick_aria": "主要搜尋方式",
        "lead": (
            "寶可夢人孔蓋（Pokéfuta）是印有寶可夢圖案的人孔蓋。"
            "從北海道到沖繩，日本47個都道府縣中有{prefs}個設有共{total}個。"
            "本圖鑑整理了每一個設置地點、蓋上的寶可夢，以及粉絲拍攝的照片"
        ),
        "lead_popular": "，包括<b>{names}</b>等共{npoke}種寶可夢。",
        "lead_end": "。",
        "mosaic_note": "最新粉絲照片（{date}更新）",
        "map_pin_title": "{pref}：{count}個寶可夢人孔蓋——在地圖上查看",
        "map_aria": "各都道府縣寶可夢人孔蓋地圖",
        "map_cta": "🗺 開啟全螢幕地圖",
        "eyebrow": "寶可夢人孔蓋圖鑑",
        "h1": "用地圖與列表探索日本全國{total}個寶可夢人孔蓋",
        "ways_title": "選擇搜尋方式",
        "way_map_title": "地圖・目前位置",
        "way_map_text": "在日本地圖上確認設置地點，找出離你最近的寶可夢人孔蓋。",
        "way_map_open": "開啟地圖",
        "way_map_theme": "依主題篩選",
        "way_pref_title": "依都道府縣",
        "way_pref_text": "依地區瀏覽設有寶可夢人孔蓋的{prefs}個都道府縣。",
        "way_pokemon_title": "依寶可夢",
        "way_pokemon_text": "從{npoke}種寶可夢中，找出你喜歡的那一個。",
        "way_theme_title": "依主題",
        "way_theme_text": "道路驛站、世界遺產、離島等，依旅遊目的尋找。",
        "new_title": "新設置的寶可夢人孔蓋",
        "new_small": "最近{days}天新增{n}個",
        "photos_title": "最新粉絲照片",
        "photos_cta": "到寶可夢人孔蓋寫真館投稿照片",
        "photos_empty": "目前還沒有照片。歡迎投稿第一張！",
        "photos_lead": "從最近的投稿中，由北到南依地區挑選，避免集中在同一地區。",
        "photos_coverage": "粉絲們目前已拍攝了{n}個地點。",
        "alt_photo": "{where}的寶可夢人孔蓋（{names}）粉絲照片",
        "alt_photo_noname": "{where}的寶可夢人孔蓋粉絲照片",
        "alt_poke": "{pref}的{name}寶可夢人孔蓋",
        "events_note": "活動名稱與內容為日文。",
        "events_show_all": "顯示全部（{n}個）",
        "pref_text": (
            "日本47個都道府縣中，有{prefs}個設有寶可夢人孔蓋。"
            "依地區由北到南排列，並標示各地的數量。"
        ),
        "pref_none": "截至{month}，{places}尚未設置寶可夢人孔蓋。",
        "pref_more": "47個都道府縣一覽",
        "poke_count": "{n}個",
        "poke_all": "全部寶可夢",
        "purpose_title": "依目的尋找",
        "purpose_theme": "依主題",
        "purpose_theme_more": "在地圖上查看",
        "purpose_pokemon": "設置最多的寶可夢",
        "regions": {
            "北海道・東北": "北海道・東北", "関東": "關東", "中部": "中部", "近畿": "近畿",
            "中国": "中國", "四国": "四國", "九州・沖縄": "九州・沖繩",
        },
    },
    "zh-CN": {
        "html_lang": "zh-CN",
        "og_locale": "zh_CN",
        "page_title": "宝可梦井盖图鉴｜日本全国宝可梦井盖（Pokéfuta）一览・地图",
        "keywords": "宝可梦井盖,Pokéfuta,Poké Lids,日本,地图,旅游,都道府县",
        "site_name": "宝可梦井盖图鉴",
        "lid": "宝可梦井盖",
        "sep": "、",
        "description": (
            "日本{prefs}个都道府县共{total}个宝可梦井盖（Pokéfuta）全收录。"
            "附粉丝拍摄的照片、地图、都道府县一览和宝可梦索引，方便规划旅程。"
        ),
        "short_description": "日本{prefs}个都道府县共{total}个宝可梦井盖，附粉丝照片和地图。",
        "ld_map": "宝可梦井盖地图",
        "ld_pokemon": "按宝可梦查看宝可梦井盖",
        "ld_stats": "宝可梦井盖统计",
        "ld_prefs": "设有宝可梦井盖的都道府县",
        "ld_pref_item": "{pref}的宝可梦井盖（{count}个）",
        "stat_lids": "个井盖",
        "stat_prefs": "个都道府县",
        "stat_pokemon": "种宝可梦",
        "stat_photos": "张粉丝照片",
        "quick_map": "用地图查找",
        "quick_pref": "按都道府县",
        "quick_pokemon": "按宝可梦",
        "quick_theme": "按主题",
        "quick_aria": "主要查找方式",
        "lead": (
            "宝可梦井盖（Pokéfuta）是印有宝可梦图案的井盖。"
            "从北海道到冲绳，日本47个都道府县中有{prefs}个设有共{total}个。"
            "本图鉴收录了每一个设置地点、井盖上的宝可梦，以及粉丝拍摄的照片"
        ),
        "lead_popular": "，包括<b>{names}</b>等共{npoke}种宝可梦。",
        "lead_end": "。",
        "mosaic_note": "最新粉丝照片（{date}更新）",
        "map_pin_title": "{pref}：{count}个宝可梦井盖——在地图上查看",
        "map_aria": "各都道府县宝可梦井盖地图",
        "map_cta": "🗺 打开全屏地图",
        "eyebrow": "宝可梦井盖图鉴",
        "h1": "用地图和列表探索日本全国{total}个宝可梦井盖",
        "ways_title": "选择查找方式",
        "way_map_title": "地图・当前位置",
        "way_map_text": "在日本地图上确认设置地点，找到离你最近的宝可梦井盖。",
        "way_map_open": "打开地图",
        "way_map_theme": "按主题筛选",
        "way_pref_title": "按都道府县",
        "way_pref_text": "按地区浏览设有宝可梦井盖的{prefs}个都道府县。都道府县页面为日文。",
        "way_pokemon_title": "按宝可梦",
        "way_pokemon_text": "从{npoke}种宝可梦中，找到你喜欢的那一个。",
        "way_theme_title": "按主题",
        "way_theme_text": "道路休息站、世界遗产、离岛等，按旅行目的查找。",
        "new_title": "新设置的宝可梦井盖",
        "new_small": "最近{days}天新增{n}个",
        "photos_title": "最新粉丝照片",
        "photos_cta": "到宝可梦井盖写真馆投稿照片",
        "photos_empty": "还没有照片。欢迎投稿第一张！",
        "photos_lead": "从最近的投稿中，由北到南按地区挑选，避免集中在同一地区。",
        "photos_coverage": "粉丝们目前已拍摄了{n}个地点。",
        "alt_photo": "{where}的宝可梦井盖（{names}）粉丝照片",
        "alt_photo_noname": "{where}的宝可梦井盖粉丝照片",
        "alt_poke": "{pref}的{name}宝可梦井盖",
        "events_note": "活动名称和内容为日文。",
        "events_show_all": "显示全部（{n}个）",
        "pref_text": (
            "日本47个都道府县中，有{prefs}个设有宝可梦井盖。"
            "按地区由北到南排列，并标出各地的数量。都道府县页面为日文。"
        ),
        "pref_none": "截至{month}，{places}尚未设置宝可梦井盖。",
        "pref_more": "47个都道府县一览（日文）",
        "poke_count": "{n}个",
        "poke_all": "全部宝可梦",
        "purpose_title": "按目的查找",
        "purpose_theme": "按主题",
        "purpose_theme_more": "在地图上查看",
        "purpose_pokemon": "设置最多的宝可梦",
        "regions": {
            "北海道・東北": "北海道・东北", "関東": "关东", "中部": "中部", "近畿": "近畿",
            "中国": "中国", "四国": "四国", "九州・沖縄": "九州・冲绳",
        },
    },
    "ko": {
        "html_lang": "ko",
        "og_locale": "ko_KR",
        "page_title": "포켓몬 맨홀 도감 | 일본 전국 포켓몬 맨홀(포케후타) 목록・지도",
        "keywords": "포켓몬 맨홀,포케후타,Pokéfuta,Poké Lids,일본,지도,여행,도도부현",
        "site_name": "포켓몬 맨홀 도감",
        "lid": "포켓몬 맨홀",
        "sep": ", ",
        "description": (
            "일본 {prefs}개 도도부현에 있는 포켓몬 맨홀(포케후타) {total}개를 모두 모았습니다. "
            "팬이 찍은 사진, 지도, 도도부현 목록, 포켓몬별 목록으로 여행 계획에 활용하세요."
        ),
        "short_description": "일본 {prefs}개 도도부현의 포켓몬 맨홀 {total}개를 팬 사진과 지도로 소개합니다.",
        "ld_map": "포켓몬 맨홀 지도",
        "ld_pokemon": "포켓몬별 포켓몬 맨홀",
        "ld_stats": "포켓몬 맨홀 통계",
        "ld_prefs": "포켓몬 맨홀이 있는 도도부현",
        "ld_pref_item": "{pref}의 포켓몬 맨홀({count}개)",
        "stat_lids": "개 맨홀",
        "stat_prefs": "개 도도부현",
        "stat_pokemon": "종 포켓몬",
        "stat_photos": "장 팬 사진",
        "quick_map": "지도로 찾기",
        "quick_pref": "도도부현별",
        "quick_pokemon": "포켓몬별",
        "quick_theme": "테마별",
        "quick_aria": "주요 검색 방법",
        "lead": (
            "포켓몬 맨홀(포케후타)은 포켓몬이 그려진 맨홀 뚜껑입니다. "
            "홋카이도부터 오키나와까지, 일본 47개 도도부현 중 {prefs}곳에 {total}개가 설치되어 있습니다. "
            "이 도감은 모든 설치 장소와 맨홀에 그려진 포켓몬, 팬들이 찍은 사진을 모았습니다"
        ),
        "lead_popular": ". <b>{names}</b> 등 모두 {npoke}종의 포켓몬이 있습니다.",
        "lead_end": ".",
        "mosaic_note": "최신 팬 사진({date} 업데이트)",
        "map_pin_title": "{pref}: 포켓몬 맨홀 {count}개 — 지도에서 보기",
        "map_aria": "도도부현별 포켓몬 맨홀 지도",
        "map_cta": "🗺 전체 화면 지도 열기",
        "eyebrow": "포켓몬 맨홀 도감",
        "h1": "일본 전국 포켓몬 맨홀 {total}개를 지도와 목록으로 찾아보세요",
        "ways_title": "찾는 방법 고르기",
        "way_map_title": "지도・현재 위치",
        "way_map_text": "일본 지도에서 설치 장소를 확인하고, 가장 가까운 포켓몬 맨홀을 찾아보세요.",
        "way_map_open": "지도 열기",
        "way_map_theme": "테마로 좁히기",
        "way_pref_title": "도도부현별",
        "way_pref_text": "포켓몬 맨홀이 있는 {prefs}개 도도부현을 지역별로 볼 수 있습니다. 도도부현 페이지는 일본어입니다.",
        "way_pokemon_title": "포켓몬별",
        "way_pokemon_text": "{npoke}종의 포켓몬 중에서 좋아하는 포켓몬을 찾아보세요.",
        "way_theme_title": "테마별",
        "way_theme_text": "도로 휴게소, 세계유산, 낙도 등 여행 목적에 맞춰 찾아보세요.",
        "new_title": "새로 설치된 포켓몬 맨홀",
        "new_small": "최근 {days}일 동안 {n}개",
        "photos_title": "최신 팬 사진",
        "photos_cta": "포켓몬 맨홀 사진관에 사진 올리기",
        "photos_empty": "아직 사진이 없습니다. 첫 사진을 올려 주세요.",
        "photos_lead": "최근 올라온 사진을 북쪽부터 지역별로 골라, 한 지역에 치우치지 않게 보여 줍니다.",
        "photos_coverage": " 지금까지 팬들이 {n}곳을 촬영했습니다.",
        "alt_photo": "{where}의 포켓몬 맨홀({names}) 팬 사진",
        "alt_photo_noname": "{where}의 포켓몬 맨홀 팬 사진",
        "alt_poke": "{pref}의 {name} 포켓몬 맨홀",
        "events_note": "이벤트 이름과 내용은 일본어입니다.",
        "events_show_all": "모두 보기({n}개)",
        "pref_text": (
            "일본 47개 도도부현 중 {prefs}곳에 포켓몬 맨홀이 있습니다. "
            "지역별로 북쪽부터 나열하고, 각 도도부현의 개수를 함께 적었습니다. 도도부현 페이지는 일본어입니다."
        ),
        "pref_none": "{month} 기준으로 {places}에는 포켓몬 맨홀이 없습니다.",
        "pref_more": "47개 도도부현 목록(일본어)",
        "poke_count": "{n}개",
        "poke_all": "모든 포켓몬",
        "purpose_title": "목적별로 찾기",
        "purpose_theme": "테마별",
        "purpose_theme_more": "지도에서 보기",
        "purpose_pokemon": "많이 설치된 포켓몬",
        "regions": {
            "北海道・東北": "홋카이도・도호쿠", "関東": "간토", "中部": "주부", "近畿": "긴키",
            "中国": "주고쿠", "四国": "시코쿠", "九州・沖縄": "규슈・오키나와",
        },
    },
}

# pokemon_metadata.json と prefectures.json での言語キー
NAME_KEYS = {"en": "en", "zh-TW": "zh-Hant", "zh-CN": "zh-Hans", "ko": "ko"}
# リージョンフォーム（アローラなど）の付け方。英語は前に付ける
FORM_PREFIX = {
    "en": {"alola": "Alolan ", "galar": "Galarian ", "hisui": "Hisuian ", "paldea": "Paldean "},
    "zh-TW": {"alola": "阿羅拉", "galar": "伽勒爾", "hisui": "洗翠", "paldea": "帕底亞"},
    "zh-CN": {"alola": "阿罗拉", "galar": "伽勒尔", "hisui": "洗翠", "paldea": "帕底亚"},
    "ko": {"alola": "알로라 ", "galar": "가라르 ", "hisui": "히스이 ", "paldea": "팔데아 "},
}
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]


def month_label(lang: str, year: int, month: int) -> str:
    """「October 2026」「2026年10月」「2026년 10월」。"""
    if lang == "en":
        return f"{EN_MONTHS[month - 1]} {year}"
    if lang == "ko":
        return f"{year}년 {month}월"
    return f"{year}年{month}月"


def day_label(lang: str, month: int, day: int) -> str:
    """「Oct 12」「10月12日」「10월 12일」。"""
    if lang == "en":
        return f"{EN_MONTHS[month - 1][:3]} {day}"
    if lang == "ko":
        return f"{month}월 {day}일"
    return f"{month}月{day}日"


def join_places(lang: str, names: list[str]) -> str:
    """県名の並び。英語だけ「A, B and C」。"""
    if lang == "en":
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return str(TEXT[lang]["sep"]).join(names)
