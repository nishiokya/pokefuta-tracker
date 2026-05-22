#!/usr/bin/env python3
"""Generate apps/web/index.template.html from apps/web/index.html.

Substitutions performed:
  - <head> meta strings → %%KEY%% markers
  - Add %%I18N_OBJECT%% injection for JS runtime strings
  - const UI_TEXT = { ... } → const UI_TEXT = window.I18N.UI;
  - JS functions modified to use window.I18N.xxx
  - HTML body display strings → %%KEY%% markers
  - ./ relative paths → %%BASE_PATH%% for subdir support
  - Add hreflang <link> tags
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent
src_path = ROOT / 'apps' / 'web' / 'index.html'
out_path = ROOT / 'apps' / 'web' / 'index.template.html'

t = src_path.read_text(encoding='utf-8')

# ──────────────────────────────────────────
# A. <head> meta strings
# ──────────────────────────────────────────

t = t.replace('<html lang="ja">', '<html lang="%%LANG%%">', 1)

t = t.replace(
    '  <title>ポケふたマップ｜全国のポケモンマンホール一覧・地図</title>',
    '  <title>%%PAGE_TITLE%%</title>', 1
)
t = t.replace(
    '  <meta name="description" content="全国のポケふた・ポケモンマンホールを地図で探せるマップサービスです。都道府県別の一覧、設置場所、近くのポケふた探しに対応しています。">',
    '  <meta name="description" content="%%META_DESCRIPTION%%">', 1
)
t = t.replace(
    '  <meta name="keywords" content="ポケふた,ポケモンマンホール,マンホール,ポケモン,聖地巡礼,地図">',
    '  <meta name="keywords" content="%%META_KEYWORDS%%">', 1
)
t = t.replace(
    '  <meta property="og:locale" content="ja_JP">',
    '  <meta property="og:locale" content="%%OG_LOCALE%%">', 1
)
t = t.replace(
    '  <meta property="og:title" content="ポケふたマップ｜全国のポケモンマンホール一覧・地図">',
    '  <meta property="og:title" content="%%PAGE_TITLE%%">', 1
)
t = t.replace(
    '  <meta property="og:description" content="全国のポケふた・ポケモンマンホールを地図で探せるマップサービスです。都道府県別の一覧、設置場所、近くのポケふた探しに対応しています。">',
    '  <meta property="og:description" content="%%META_DESCRIPTION%%">', 1
)
t = t.replace(
    '  <meta property="og:url" content="https://data.pokefuta.com/">',
    '  <meta property="og:url" content="%%CANONICAL_URL%%">', 1
)
t = t.replace(
    '  <meta name="twitter:title" content="ポケふたマップ｜全国のポケモンマンホール一覧・地図">',
    '  <meta name="twitter:title" content="%%PAGE_TITLE%%">', 1
)
t = t.replace(
    '  <meta name="twitter:description" content="全国のポケふた・ポケモンマンホールを地図で探せるマップサービスです。都道府県別の一覧、設置場所、近くのポケふた探しに対応しています。">',
    '  <meta name="twitter:description" content="%%META_DESCRIPTION%%">', 1
)
t = t.replace(
    '  <link rel="canonical" href="https://data.pokefuta.com/">',
    '  <link rel="canonical" href="%%CANONICAL_URL%%">\n'
    '  <link rel="alternate" hreflang="ja"      href="https://data.pokefuta.com/">\n'
    '  <link rel="alternate" hreflang="en"      href="https://data.pokefuta.com/en/">\n'
    '  <link rel="alternate" hreflang="zh-TW"   href="https://data.pokefuta.com/zh-TW/">\n'
    '  <link rel="alternate" hreflang="zh-Hans" href="https://data.pokefuta.com/zh-CN/">\n'
    '  <link rel="alternate" hreflang="ko"      href="https://data.pokefuta.com/ko/">\n'
    '  <link rel="alternate" hreflang="x-default" href="https://data.pokefuta.com/">',
    1
)

# ──────────────────────────────────────────
# B. Inject window.I18N before window.PREFECTURE_CODE_MAP
# ──────────────────────────────────────────

I18N_INJECTION = (
    '    // i18n: build-time injected per language\n'
    '    window.I18N = %%I18N_OBJECT%%;\n\n'
)
t = t.replace(
    '    window.PREFECTURE_CODE_MAP = Object.freeze({',
    I18N_INJECTION + '    window.PREFECTURE_CODE_MAP = Object.freeze({',
    1
)

# ──────────────────────────────────────────
# C. buildPrefecturePageMeta — use window.I18N
# ──────────────────────────────────────────

OLD_PREF_META = '''    window.buildPrefecturePageMeta = function(prefecture) {
      const title = prefecture
        ? `${prefecture}のポケふた一覧｜ポケモンマンホール設置場所マップ`
        : 'ポケふたマップ｜全国のポケモンマンホール一覧・地図';
      const description = prefecture
        ? `${prefecture}にあるポケモンマンホール「ポケふた」の設置場所を地図で確認できます。登場ポケモンや市町村別の場所を見ながら、旅行やポケふた巡りの計画に使えます。`
        : '全国のポケふた・ポケモンマンホールを地図で探せるマップサービスです。都道府県別の一覧、設置場所、近くのポケふた探しに対応しています。';
      const keywords = prefecture
        ? `ポケふた,${prefecture},ポケモンマンホール,マンホール,設置場所,地図,旅行,観光`
        : 'ポケふた,ポケモンマンホール,マンホール,ポケモン,聖地巡礼,地図';'''

NEW_PREF_META = '''    window.buildPrefecturePageMeta = function(prefecture) {
      const I = window.I18N;
      const title = prefecture
        ? `${prefecture}${I.prefTitleSuffix}`
        : I.defaultTitle;
      const description = prefecture
        ? `${I.prefDescPrefix}${prefecture}${I.prefDescSuffix}`
        : I.defaultDescription;
      const keywords = prefecture
        ? `${I.prefKeywordsPrefix}${prefecture}${I.prefKeywordsSuffix}`
        : I.defaultKeywords;'''

t = t.replace(OLD_PREF_META, NEW_PREF_META, 1)

# ──────────────────────────────────────────
# D. applyManholePageMeta — use window.I18N
# ──────────────────────────────────────────

OLD_MANHOLE_META_1 = "      let pokemonText = 'ポケモン';"
NEW_MANHOLE_META_1 = "      const I = window.I18N;\n      let pokemonText = I.defaultPokemonText;"
t = t.replace(OLD_MANHOLE_META_1, NEW_MANHOLE_META_1, 1)

OLD_MANHOLE_TITLE = '''      const title = locationPart
        ? `${pokemonText}のポケふた | ${locationPart} | Pokefuta Map`
        : `${pokemonText}のポケふた | Pokefuta Map`;'''
NEW_MANHOLE_TITLE = '''      const title = locationPart
        ? `${pokemonText}${I.manholeTitleInfix}${locationPart} | Pokefuta Map`
        : `${pokemonText}${I.manholeTitleInfix}Pokefuta Map`;'''
t = t.replace(OLD_MANHOLE_TITLE, NEW_MANHOLE_TITLE, 1)

OLD_MANHOLE_DESC = '''      // description: {都道府県}{市区町村}にある{ポケモン名}（English）のポケふた。場所・写真・訪問記録を地図で確認できます。
      const placeText = prefecture && city ? `${prefecture}${city}` : (prefecture || '');
      const pokemonWithEn = pokemonTextEn ? `${pokemonText}（${pokemonTextEn}）` : pokemonText;
      const description = placeText
        ? `${placeText}にある${pokemonWithEn}のポケふた。場所・写真・訪問記録を地図で確認できます。`
        : `${pokemonWithEn}のポケふた。場所・写真・訪問記録を地図で確認できます。`;'''
NEW_MANHOLE_DESC = '''      const placeText = prefecture && city ? `${prefecture}${city}` : (prefecture || '');
      const pokemonWithEn = pokemonTextEn ? `${pokemonText}（${pokemonTextEn}）` : pokemonText;
      const description = placeText
        ? I.manholeDescTemplate.replace('{place}', placeText).replace('{pokemon}', pokemonWithEn)
        : I.manholeDescNoPlaceTemplate.replace('{pokemon}', pokemonWithEn);'''
t = t.replace(OLD_MANHOLE_DESC, NEW_MANHOLE_DESC, 1)

OLD_KEYWORDS_BASE = "      // keywords: include multilingual Pokemon names\n      const keywordParts = ['ポケふた'];"
NEW_KEYWORDS_BASE = "      const keywordParts = [I.baseKeyword];"
t = t.replace(OLD_KEYWORDS_BASE, NEW_KEYWORDS_BASE, 1)

OLD_KEYWORDS_TAIL = "      keywordParts.push('ポケモンマンホール', 'Pokemon Manhole', 'マンホール', '聖地巡礼', '地図');"
NEW_KEYWORDS_TAIL = "      keywordParts.push(...I.manholeKeywordsEnd);"
t = t.replace(OLD_KEYWORDS_TAIL, NEW_KEYWORDS_TAIL, 1)

# ──────────────────────────────────────────
# E. applyDefaultMeta — use window.I18N
# ──────────────────────────────────────────

OLD_DEFAULT_META = '''    window.applyDefaultMeta = function() {
      const defaultMeta = {
        title: 'ポケふたマップ｜全国のポケモンマンホール一覧・地図',
        description: '全国のポケふた・ポケモンマンホールを地図で探せるマップサービスです。都道府県別の一覧、設置場所、近くのポケふた探しに対応しています。',
        keywords: 'ポケふた,ポケモンマンホール,マンホール,ポケモン,聖地巡礼,地図',
        canonicalUrl: window.SITE_BASE_URL
      };'''
NEW_DEFAULT_META = '''    window.applyDefaultMeta = function() {
      const I = window.I18N;
      const defaultMeta = {
        title: I.defaultTitle,
        description: I.defaultDescription,
        keywords: I.defaultKeywords,
        canonicalUrl: window.SITE_BASE_URL
      };'''
t = t.replace(OLD_DEFAULT_META, NEW_DEFAULT_META, 1)

# ──────────────────────────────────────────
# F. applyManholeJsonLd — use window.I18N, remove streetAddress
# ──────────────────────────────────────────

OLD_JSONLD_VARS = '''      const placeText = [manhole.prefecture, manhole.city].filter(Boolean).join('');
      const titleBase = manhole.title || `ポケふた ${manhole.id}`;
      const baseDescription = `${placeText ? `${placeText}の` : ''}ポケモンマンホール（ポケふた）。`;

      // Enhanced Pokemon description with multilingual names
      let pokemonDescription = '';
      if (cleanPokemons.length > 0) {
        const pokemonInfoList = cleanPokemons.map(nameJa => {
          const meta = getPokemonMetadata(nameJa);
          if (meta && meta.names && meta.names.en) {
            return `${nameJa} (${meta.names.en})`;
          }
          return nameJa;
        });
        pokemonDescription = `登場ポケモン: ${pokemonInfoList.join(', ')}`;
      }'''
NEW_JSONLD_VARS = '''      const I = window.I18N;
      const placeText = [manhole.prefecture, manhole.city].filter(Boolean).join('');
      const titleBase = manhole.title || `${I.manholeTitle} ${manhole.id}`;
      const baseDescription = placeText
        ? I.jsonLdDescTemplate.replace('{place}', placeText)
        : I.jsonLdDescNoPlace;

      let pokemonDescription = '';
      if (cleanPokemons.length > 0) {
        const pokemonInfoList = cleanPokemons.map(nameJa => {
          const meta = getPokemonMetadata(nameJa);
          if (meta && meta.names && meta.names.en) {
            return `${nameJa} (${meta.names.en})`;
          }
          return nameJa;
        });
        pokemonDescription = `${I.pokemonDescPrefix}${pokemonInfoList.join(', ')}`;
      }'''
t = t.replace(OLD_JSONLD_VARS, NEW_JSONLD_VARS, 1)

OLD_JSONLD_ADDRESS = '''        'address': {
          '@type': 'PostalAddress',
          'addressRegion': manhole.prefecture || '',
          'addressLocality': manhole.city || '',
          'streetAddress': manhole.address || ''
        },'''
NEW_JSONLD_ADDRESS = '''        'address': {
          '@type': 'PostalAddress',
          'addressRegion': manhole.prefecture || '',
          'addressLocality': manhole.city || ''
        },'''
t = t.replace(OLD_JSONLD_ADDRESS, NEW_JSONLD_ADDRESS, 1)

OLD_JSONLD_KEYWORDS = "      const keywordsArray = ['ポケふた', 'ポケモンマンホール', 'Pokemon Manhole', titleBase];"
NEW_JSONLD_KEYWORDS = "      const keywordsArray = [I.baseKeyword, I.manholeKeyword, 'Pokemon Manhole', titleBase];"
t = t.replace(OLD_JSONLD_KEYWORDS, NEW_JSONLD_KEYWORDS, 1)

# ──────────────────────────────────────────
# G. CSS/asset paths: ./ → %%BASE_PATH%%
# ──────────────────────────────────────────

# CSS links in <head>
t = t.replace(
    '  <link rel="stylesheet" href="./assets/theme.css" />',
    '  <link rel="stylesheet" href="%%BASE_PATH%%assets/theme.css" />', 1
)
t = t.replace(
    '  <link rel="stylesheet" href="./assets/map.css" />',
    '  <link rel="stylesheet" href="%%BASE_PATH%%assets/map.css" />', 1
)
t = t.replace(
    '  <link rel="stylesheet" href="./assets/pokefuta-map.css" />',
    '  <link rel="stylesheet" href="%%BASE_PATH%%assets/pokefuta-map.css" />', 1
)
t = t.replace(
    '  <link rel="icon" href="./assets/pokefuta-marker.svg" type="image/svg+xml" />',
    '  <link rel="icon" href="%%BASE_PATH%%assets/pokefuta-marker.svg" type="image/svg+xml" />', 1
)
# Leaflet marker icon
t = t.replace(
    "      iconUrl: './assets/pokefuta-marker.svg',",
    "      iconUrl: '%%BASE_PATH%%assets/pokefuta-marker.svg',", 1
)
# HTML img src in body
t = t.replace('src="./assets/icon-map.svg"', 'src="%%BASE_PATH%%assets/icon-map.svg"')
t = t.replace('src="./assets/icon-fire.svg"', 'src="%%BASE_PATH%%assets/icon-fire.svg"')
t = t.replace('src="./assets/icon-current-location.svg"', 'src="%%BASE_PATH%%assets/icon-current-location.svg"')
# JS strings with assets
t = t.replace("'./assets/icon-fire.svg'", "'%%BASE_PATH%%assets/icon-fire.svg'")
# Data files
t = t.replace(
    "        const response = await fetch('./latest-manhole-photos.json', { cache: 'no-store' });",
    "        const response = await fetch('%%BASE_PATH%%latest-manhole-photos.json', { cache: 'no-store' });", 1
)
t = t.replace(
    "        const res = await fetch('./pokemon_metadata.json', { cache: 'default' });",
    "        const res = await fetch('%%BASE_PATH%%pokemon_metadata.json', { cache: 'default' });", 1
)
# manhole image path in JS function
t = t.replace(
    "      return safeId ? `./manhole/image/${encodeURIComponent(safeId)}_latest.jpeg` : '';",
    "      return safeId ? `%%BASE_PATH%%manhole/image/${encodeURIComponent(safeId)}_latest.jpeg` : '';", 1
)
# footer data export links
t = t.replace(
    '      <a href="./pokefuta.ndjson" target="_blank" rel="noopener">NDJSON</a>',
    '      <a href="%%BASE_PATH%%pokefuta.ndjson" target="_blank" rel="noopener">NDJSON</a>', 1
)
t = t.replace(
    '      <a href="./pokefuta.kml" target="_blank" rel="noopener">KML</a>',
    '      <a href="%%BASE_PATH%%pokefuta.kml" target="_blank" rel="noopener">KML</a>', 1
)

# ──────────────────────────────────────────
# H. const UI_TEXT → window.I18N.UI
# ──────────────────────────────────────────

# Find and replace the entire UI_TEXT block
ui_text_old = '''    // ==== 単一言語 (日本語) 用 UI ラベル定数 ====
    const UI_TEXT = {
      recentLabel: '🆕 直近1ヶ月',
      prefectureFilter: '都道府県で絞り込み',
      allPrefectures: 'すべての都道府県',
      prefectureCount: '都道府県別ポケふた数',
      searchPrefecture: '都道府県を検索...',
      codeHeader: 'コード',
      prefectureHeader: '都道府県',
      countHeader: 'ポケふた数',
      siteHeader: 'サイト',
      pokemonFilter: 'ポケモンで絞り込み',
      searchPokemon: 'ポケモンを検索...',
      showAll: '🔄 すべて表示',
      totalCount: '総数:',
      visibleCount: '表示:',
      cityCount: '市町村:',
      idLabel: 'ID:',
      titleLabel: 'タイトル:',
      prefectureLabel: '都道府県:',
      pokemonLabel: 'ポケモン:',
      cityLabel: '市町村:',
      officialDetail: '📝 公式詳細',
      officialDetailCta: '公式詳細を見る',
      detailPageCta: '詳細ページを見る',
      prefectureSite: 'サイト'
    };

    // 初期テキストは既に HTML に記述しているため updateUIText は不要
    function updateUIText() { /* no-op (多言語削除) */ }'''
ui_text_new = "    // UI labels: sourced from build-time injected window.I18N.UI\n    const UI_TEXT = window.I18N.UI;\n\n    function updateUIText() { /* no-op */ }"
t = t.replace(ui_text_old, ui_text_new, 1)

# ──────────────────────────────────────────
# I. buildPokefutaPopup — use window.I18N
# ──────────────────────────────────────────

t = t.replace(
    "      const prefecture = d.prefecture || '不明';",
    "      const I = window.I18N;\n      const prefecture = d.prefecture || I.unknownPref;", 1
)
t = t.replace(
    "        : '<span class=\"travel-popup-pokemon\">ポケモン未設定</span>';",
    "        : `<span class=\"travel-popup-pokemon\">${I.noPokemon}</span>`;", 1
)
t = t.replace(
    "      const photoAlt = `${d.title || 'ポケふた'}の写真`;",
    "      const photoAlt = `${d.title || I.manholeTitle}${I.photoAltSuffix}`;", 1
)
t = t.replace(
    "        photoDate ? `<span class=\"travel-popup-photo-date\">撮影日 ${escapeHtml(photoDate)}</span>` : '',",
    "        photoDate ? `<span class=\"travel-popup-photo-date\">${I.photoDatePrefix}${escapeHtml(photoDate)}</span>` : '',", 1
)
t = t.replace(
    "      const shareTitle = `${d.title || 'ポケふた'} | ポケふたマップ`;",
    "      const shareTitle = `${d.title || I.manholeTitle}${I.shareTitleSuffix}`;", 1
)
t = t.replace(
    "      const _shareHashtags = (_titleHashtags + ' #ポケふた #ポケモンマンホール').trim();",
    "      const _shareHashtags = (_titleHashtags + I.shareHashtags).trim();", 1
)
t = t.replace(
    "        ? (titles[0].emoji ? titles[0].emoji + ' ' : '') + titles[0].label + 'のポケふた！\\n' + _shareHashtags",
    "        ? (titles[0].emoji ? titles[0].emoji + ' ' : '') + titles[0].label + I.shareTextSuffix + _shareHashtags",
    1
)
t = t.replace(
    '        <div class="popup-photo travel-popup-photo" aria-label="マンホール写真">',
    '        <div class="popup-photo travel-popup-photo" aria-label="${I.manholePhotoAria}">', 1
)
t = t.replace(
    '            <b>写真募集中</b>\n            <span>このポケふたの写真はまだありません。</span>\n            <a href="https://pokefuta.com/visits" target="_blank" rel="noopener noreferrer" class="popup-link popup-link--upload">写真を投稿</a>',
    '            <b>${I.photoWanted}</b>\n            <span>${I.photoMissing}</span>\n            <a href="https://pokefuta.com/visits" target="_blank" rel="noopener noreferrer" class="popup-link popup-link--upload">${I.uploadPhoto}</a>',
    1
)
t = t.replace(
    '            <h3 class="travel-popup-title">${escapeHtml(d.title || \'ポケふた\')}</h3>',
    '            <h3 class="travel-popup-title">${escapeHtml(d.title || I.manholeTitle)}</h3>', 1
)
t = t.replace(
    '            <div class="travel-popup-pokemon-list" aria-label="登場ポケモン">${pokemonsHtml}</div>',
    '            <div class="travel-popup-pokemon-list" aria-label="${I.pokemonListAria}">${pokemonsHtml}</div>', 1
)
t = t.replace(
    '              <button class="travel-popup-action travel-popup-action--share" data-share-url="${safeShareUrl}" data-share-title="${safeShareTitle}" data-share-text="${safeShareText}" aria-label="シェア">シェア</button>',
    '              <button class="travel-popup-action travel-popup-action--share" data-share-url="${safeShareUrl}" data-share-title="${safeShareTitle}" data-share-text="${safeShareText}" aria-label="${I.shareButton}">${I.shareButton}</button>',
    1
)

# ──────────────────────────────────────────
# I-2. getPokemonLpUrl — Japanese → i18n-aware
# ──────────────────────────────────────────

t = t.replace(
    '''    function getPokemonLpUrl(jaName) {
      const meta = getPokemonMetadata(jaName);
      if (!meta || !meta.slug) return null;
      return `${window.SITE_BASE_URL}pokemon/${meta.slug}/`;
    }''',
    '''    window.getPokemonLpUrl = function(jaName) {
      const meta = getPokemonMetadata(jaName);
      if (!meta || !meta.slug) return null;
      const lang = (window.I18N && window.I18N.lang) || 'ja';
      const prefix = lang === 'ja' ? '' : lang + '/';
      return `${window.SITE_ROOT_URL}${prefix}pokemon/${meta.slug}/`;
    };''',
    1
)
t = t.replace(
    '''        ? pokemons.map(pokemon => {
            const url = getPokemonLpUrl(pokemon);
            return url
              ? `<a href="${escapeHtml(url)}" class="travel-popup-pokemon" target="_blank" rel="noopener noreferrer">${escapeHtml(pokemon)}</a>`
              : `<span class="travel-popup-pokemon">${escapeHtml(pokemon)}</span>`;
          }).join('')''',
    '''        ? pokemons.map(pokemon => {
            const displayName = escapeHtml(getPokemonDisplayName(pokemon));
            const url = getPokemonLpUrl(pokemon);
            return url
              ? `<a href="${escapeHtml(url)}" class="travel-popup-pokemon" target="_blank" rel="noopener noreferrer">${displayName}</a>`
              : `<span class="travel-popup-pokemon">${displayName}</span>`;
          }).join('')''',
    1
)

# ──────────────────────────────────────────
# J. buildPokemonInfoCards — use window.I18N
# ──────────────────────────────────────────

t = t.replace(
    "            ${types ? `<div class=\"pokemon-info-row\"><strong>タイプ:</strong> ${types}</div>` : ''}",
    "            ${types ? `<div class=\"pokemon-info-row\"><strong>${I.typeLabel}</strong> ${types}</div>` : ''}",
    1
)
t = t.replace(
    "            ${meta.generation ? `<div class=\"pokemon-info-row\"><strong>世代:</strong> 第${meta.generation}世代</div>` : ''}",
    "            ${meta.generation ? `<div class=\"pokemon-info-row\"><strong>${I.genLabel}</strong> ${I.genFormat.replace('{n}', meta.generation)}</div>` : ''}",
    1
)
# Add I = window.I18N near top of buildPokemonInfoCards
t = t.replace(
    "    function buildPokemonInfoCards(pokemons) {\n      if (!pokemonMetadata || !Array.isArray(pokemons) || pokemons.length === 0) return '';",
    "    function buildPokemonInfoCards(pokemons) {\n      const I = window.I18N;\n      if (!pokemonMetadata || !Array.isArray(pokemons) || pokemons.length === 0) return '';",
    1
)

# ──────────────────────────────────────────
# K. buildSamePokemonSection — use window.I18N
# ──────────────────────────────────────────

t = t.replace(
    "          title=\"${escapeHtml(d.title || 'ポケふた')}を開く\">",
    "          title=\"${escapeHtml(d.title || I.manholeTitle)}${I.openSuffix}\">", 1
)
t = t.replace(
    "          <h5>同じポケモンのポケふた</h5>",
    "          <h5>${I.samePokemonHeading}</h5>", 1
)
# Add I = window.I18N near top of buildSamePokemonSection
t = t.replace(
    "    function buildSamePokemonSection(pokemons, currentId) {\n      if (!Array.isArray(pokemons) || pokemons.length === 0) return '';",
    "    function buildSamePokemonSection(pokemons, currentId) {\n      const I = window.I18N;\n      if (!Array.isArray(pokemons) || pokemons.length === 0) return '';",
    1
)
t = t.replace(
    "          ? d.pokemons.filter(p => !p.includes('ローカルActs')).slice(0, 2).join('・')",
    "          ? d.pokemons.filter(p => !p.includes('ローカルActs')).slice(0, 2).join(' / ')",
    1
)

# ──────────────────────────────────────────
# L. formatPhotoDate locale
# ──────────────────────────────────────────

t = t.replace(
    "      return new Intl.DateTimeFormat('ja-JP', {",
    "      return new Intl.DateTimeFormat(window.I18N.intlLocale, {", 1
)

# ──────────────────────────────────────────
# M. shareManholeUrl — clipboard states
# ──────────────────────────────────────────

t = t.replace(
    "          button.textContent = 'コピー済み';",
    "          button.textContent = window.I18N.copyDone;", 1
)
t = t.replace(
    "            button.textContent = originalText || '共有';",
    "            button.textContent = originalText || window.I18N.shareLabel;", 1
)
t = t.replace(
    "      window.prompt('共有URLをコピーしてください', url);",
    "      window.prompt(window.I18N.shareCopyPrompt, url);", 1
)

# ──────────────────────────────────────────
# N. populatePrefectureTable — use window.I18N
# ──────────────────────────────────────────

t = t.replace(
    "        let siteCell = '<span class=\"prefecture-site-link prefecture-site-link--empty\">公式サイトなし</span>';",
    "        const I = window.I18N;\n        let siteCell = `<span class=\"prefecture-site-link prefecture-site-link--empty\">${I.noSite}</span>`;",
    1
)
t = t.replace(
    "            <span class=\"${countBadgeClass}\">${count}枚</span>",
    "            <span class=\"${countBadgeClass}\">${count}${I.countSuffix}</span>", 1
)
t = t.replace(
    '          <div class="prefecture-card-gallery" aria-label="${escapeHtml(prefecture)}のマンホール写真">',
    '          <div class="prefecture-card-gallery" aria-label="${escapeHtml(prefecture)}${I.galleryAriaSuffix}">',
    1
)
t = t.replace(
    '              <button type="button" class="prefecture-card-thumb" data-manhole-id="${escapeHtml(item.id)}" aria-label="${escapeHtml(item.title)}の詳細を開く" title="${escapeHtml(item.title)}の詳細を開く">',
    '              <button type="button" class="prefecture-card-thumb" data-manhole-id="${escapeHtml(item.id)}" aria-label="${escapeHtml(item.title)}${I.openDetailSuffix}" title="${escapeHtml(item.title)}${I.openDetailSuffix}">',
    1
)
t = t.replace(
    "            title=\"${escapeHtml(item.title)}の詳細を開く\"",
    "            title=\"${escapeHtml(item.title)}${I.openDetailSuffix}\"", 1
)
t = t.replace(
    "          button.title = `${prefecture}のポケふたを地図で見る`;",
    "          button.title = I.prefCardTitleFormat.replace('{pref}', prefecture);", 1
)
t = t.replace(
    "        return `<a href=\"${href}\" data-prefecture=\"${escapeHtml(prefecture)}\">${escapeHtml(prefecture)}<span>${count}枚</span></a>`;",
    "        return `<a href=\"${href}\" data-prefecture=\"${escapeHtml(prefecture)}\">${escapeHtml(prefecture)}<span>${count}${window.I18N.countSuffix}</span></a>`;",
    1
)
t = t.replace(
    "            prefectureThumbnails[pref].push({\n            id: d.id,\n            title: d.title || 'ポケふた',",
    "            prefectureThumbnails[pref].push({\n            id: d.id,\n            title: d.title || window.I18N.manholeTitle,",
    1
)

# ──────────────────────────────────────────
# O. renderRecentAdded / renderSpotResults — use window.I18N
# ──────────────────────────────────────────

t = t.replace(
    "        emptyMessage: '直近30日の追加はありません。',",
    "        emptyMessage: window.I18N.recentEmpty,", 1
)
t = t.replace(
    "        meta: d => [d.prefecture || '不明', d.title || 'ポケふた'].join(' / '),\n        badge: () => '<img src=\"%%BASE_PATH%%assets/icon-fire.svg\" alt=\"\" aria-hidden=\"true\">NEW',\n        limit: 24\n      });\n    }\n\n    function bindSpotResultList",
    "        meta: d => [d.prefecture || window.I18N.unknownPref, d.title || window.I18N.manholeTitle].join(' / '),\n        badge: () => `<img src=\"%%BASE_PATH%%assets/icon-fire.svg\" alt=\"\" aria-hidden=\"true\">NEW`,\n        limit: 24\n      });\n    }\n\n    function bindSpotResultList",
    1
)
t = t.replace(
    "        const metaText = meta ? meta(d) : (d.title || 'ポケふた');",
    "        const metaText = meta ? meta(d) : (d.title || window.I18N.manholeTitle);", 1
)
t = t.replace(
    "            <strong>${escapeHtml(d.city || '自治体未設定')}</strong>",
    "            <strong>${escapeHtml(d.city || window.I18N.unknownCity)}</strong>", 1
)
# renderNearbyResults
t = t.replace(
    "        meta: d => [d.prefecture || '不明', d.title || 'ポケふた'].join(' / '),",
    "        meta: d => [d.prefecture || window.I18N.unknownPref, d.title || window.I18N.manholeTitle].join(' / '),",
)

# ──────────────────────────────────────────
# P. renderPrefectureSpots heading — use window.I18N
# ──────────────────────────────────────────

t = t.replace(
    "      heading.textContent = `${prefecture}のポケふた`;",
    "      heading.textContent = window.I18N.prefSpotsHeadingFormat.replace('{pref}', prefecture);", 1
)

# ──────────────────────────────────────────
# Q. initLocationSearch — use window.I18N
# ──────────────────────────────────────────

t = t.replace(
    "      const defaultLabel = label?.textContent || '近くのポケふた';",
    "      const defaultLabel = label?.textContent || window.I18N.locateLabel;", 1
)
t = t.replace(
    "          setButtonState('現在地を使えません', { resetAfter: 1800 });",
    "          setButtonState(window.I18N.locateUnavailable, { resetAfter: 1800 });", 1
)
t = t.replace(
    "        setButtonState('確認中...', { busy: true });",
    "        setButtonState(window.I18N.locateChecking, { busy: true });", 1
)
t = t.replace(
    "          setButtonState('取得できませんでした', { resetAfter: 1800 });",
    "          setButtonState(window.I18N.locateFailed, { resetAfter: 1800 });", 1
)

# ──────────────────────────────────────────
# R. initRecentFilter disabled tooltip
# ──────────────────────────────────────────

t = t.replace(
    "        toggle.title = 'データに日付フィールド (added_at / first_seen / last_seen / source_last_checked / last_updated / date) が無いため利用できません';",
    "        toggle.title = window.I18N.recentDisabledTitle;", 1
)

# ──────────────────────────────────────────
# S. HTML body static strings → %%KEY%% markers
# ──────────────────────────────────────────

t = t.replace(
    '  <main class="map-stage" aria-label="ポケふた探索マップ">',
    '  <main class="map-stage" aria-label="%%MAP_ARIA%%">', 1
)
t = t.replace(
    '      <h1 id="hero-title">全国のポケふた・ポケモンマンホールマップ</h1>',
    '      <h1 id="hero-title">%%HERO_TITLE%%</h1>', 1
)
t = t.replace(
    '      <p>旅行やお出かけのついでに、ご当地マンホール「ポケふた」を見つけよう</p>',
    '      <p>%%HERO_SUBTITLE%%</p>', 1
)
t = t.replace(
    '      <p class="map-hero-meta">📍 全国<span id="hero-city-count">0</span>の自治体に設置</p>',
    '      <p class="map-hero-meta">%%HERO_CITY_PREFIX%%<span id="hero-city-count">0</span>%%HERO_CITY_SUFFIX%%</p>',
    1
)
t = t.replace(
    '    <span id="page-title" class="sr-only">全体パネル</span>',
    '    <span id="page-title" class="sr-only">%%PANEL_TITLE%%</span>', 1
)
t = t.replace(
    '      <button type="button" id="controls-toggle" class="controls-toggle-btn" aria-label="全体パネルを開く" title="全体パネルを開く/閉じる" aria-expanded="false" aria-controls="controls-content">',
    '      <button type="button" id="controls-toggle" class="controls-toggle-btn" aria-label="%%CONTROLS_TOGGLE_ARIA%%" title="%%CONTROLS_TOGGLE_TITLE%%" aria-expanded="false" aria-controls="controls-content">',
    1
)
t = t.replace(
    '    <div id="controls-content" class="controls-content" role="region" aria-label="全体パネルの内容">',
    '    <div id="controls-content" class="controls-content" role="region" aria-label="%%PANEL_CONTENT_ARIA%%">',
    1
)
t = t.replace(
    '          <div class="sheet-action-grid" aria-label="探索メニュー">',
    '          <div class="sheet-action-grid" aria-label="%%EXPLORE_MENU_ARIA%%">', 1
)
t = t.replace(
    '            <span id="locate-button-label">近くのポケふたを探す</span>',
    '            <span id="locate-button-label">%%LOCATE_LABEL%%</span>', 1
)
t = t.replace(
    '          <h2 id="prefecture-directory-heading">都道府県別のポケふた一覧</h2>',
    '          <h2 id="prefecture-directory-heading">%%PREF_DIR_HEADING%%</h2>', 1
)
t = t.replace(
    '        <p>旅行先やお出かけ先の近くにあるポケふたを、都道府県別に探せます。</p>',
    '        <p>%%PREF_DIR_DESC%%</p>', 1
)
t = t.replace(
    '        <div id="prefecture-directory-links" class="prefecture-directory-links" aria-label="ポケふたがある都道府県"></div>',
    '        <div id="prefecture-directory-links" class="prefecture-directory-links" aria-label="%%PREF_DIR_LINKS_ARIA%%"></div>',
    1
)
t = t.replace(
    '          <h4>近くのポケふた</h4>',
    '          <h4>%%NEARBY_HEADING%%</h4>', 1
)
t = t.replace(
    '          <h4 id="recent-added-heading">新着ポケふた</h4>',
    '          <h4 id="recent-added-heading">%%RECENT_HEADING%%</h4>', 1
)
t = t.replace(
    '          <span class="badge-label" style="font-weight:600;">選択中:</span> <span class="badge-value"></span>',
    '          <span class="badge-label" style="font-weight:600;">%%BADGE_LABEL%%</span> <span class="badge-value"></span>',
    1
)
t = t.replace(
    '          <button type="button" class="badge-clear" aria-label="選択解除" onclick="clearPrefectureSelection()">×</button>',
    '          <button type="button" class="badge-clear" aria-label="%%BADGE_CLEAR_ARIA%%" onclick="clearPrefectureSelection()">×</button>',
    1
)
t = t.replace(
    '            <h4 id="prefecture-spots-heading">県内のポケふた</h4>',
    '            <h4 id="prefecture-spots-heading">%%PREF_SPOTS_HEADING%%</h4>', 1
)

# Popular Pokémon nav section
OLD_NAV = '''  <nav aria-label="人気のポケモン" style="margin:16px auto 0; max-width:960px; padding:12px 16px; background:#fff8ec; border-radius:8px; border:1px solid #e8e0d0;">
    <p style="font-size:0.85rem; font-weight:bold; color:#6F55A3; margin:0 0 4px;">人気のポケモン</p>
    <p style="margin:0 0 8px;"><a href="/pokemon/" style="font-size:0.85rem; color:#6F55A3; font-weight:bold;">→ ポケモン一覧を見る</a></p>
    <ul style="list-style:none; padding:0; margin:0; display:flex; flex-wrap:wrap; gap:6px;">
      <li><a href="/pokemon/chansey/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">ラッキー</a></li>
      <li><a href="/pokemon/lapras/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">ラプラス</a></li>
      <li><a href="/pokemon/vulpix-alola/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">アローラロコン</a></li>
      <li><a href="/pokemon/oshawott/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">ミジュマル</a></li>
      <li><a href="/pokemon/vulpix/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">ロコン</a></li>
      <li><a href="/pokemon/geodude/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">イシツブテ</a></li>
      <li><a href="/pokemon/quagsire/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">ヌオー</a></li>
      <li><a href="/pokemon/exeggutor/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">ナッシー</a></li>
      <li><a href="/pokemon/dragonite/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">カイリュー</a></li>
      <li><a href="/pokemon/slowpoke/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">ヤドン</a></li>
      <li><a href="/pokemon/sandshrew/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">サンド</a></li>
      <li><a href="/pokemon/pikachu/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">ピカチュウ</a></li>
      <li><a href="/pokemon/eevee/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">イーブイ</a></li>
      <li><a href="/pokemon/snorlax/" style="font-size:0.85rem; color:#6F55A3; text-decoration:none;">カビゴン</a></li>
    </ul>
  </nav>'''
NEW_NAV = '''  <nav aria-label="%%POPULAR_NAV_ARIA%%" style="margin:16px auto 0; max-width:960px; padding:12px 16px; background:#fff8ec; border-radius:8px; border:1px solid #e8e0d0;">
    <p style="font-size:0.85rem; font-weight:bold; color:#6F55A3; margin:0 0 4px;">%%POPULAR_HEADING%%</p>
    <p style="margin:0 0 8px;"><a href="/pokemon/" style="font-size:0.85rem; color:#6F55A3; font-weight:bold;">%%POPULAR_LINK%%</a></p>
    <ul style="list-style:none; padding:0; margin:0; display:flex; flex-wrap:wrap; gap:6px;">
%%POPULAR_ITEMS%%
    </ul>
  </nav>'''
t = t.replace(OLD_NAV, NEW_NAV, 1)

# Footer
t = t.replace(
    '      📡 データエクスポート:',
    '      %%FOOTER_EXPORT%%', 1
)

# ──────────────────────────────────────────
# Done
# ──────────────────────────────────────────

out_path.write_text(t, encoding='utf-8')
print(f'[OK] Written: {out_path}')

# Sanity check: count remaining Japanese characters
import unicodedata
jp_count = sum(
    1 for ch in t
    if '぀' <= ch <= '鿿' or '＀' <= ch <= '￯'
)
print(f'[INFO] Remaining CJK/kana characters in template: {jp_count}')
if jp_count > 0:
    # Print first 20 lines containing Japanese
    found = 0
    for i, line in enumerate(t.splitlines(), 1):
        has_jp = any('぀' <= ch <= '鿿' or '＀' <= ch <= '￯' for ch in line)
        if has_jp:
            print(f'  line {i}: {line[:120]}')
            found += 1
            if found >= 20:
                break
