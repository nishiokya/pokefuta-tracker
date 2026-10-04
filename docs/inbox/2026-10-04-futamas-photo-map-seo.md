# ふたマス専用ページ：写真・地図・検索導線

- 対象URL: https://data.pokefuta.com/characters/idolmaster/
- 公開投稿が既存キャラふたに紐づいた場合、先頭の写真をヒーロー・OGP・primaryImageOfPageで利用する。現在は愛知県常滑市の前川みく。公開写真がない場合は従来のエンブレムへ戻る。
- スマートフォンではトップに写真を配置。画像領域を予約し、ヒーローは優先読み込みする。
- ふたマスだけのページ内Leaflet地図を追加。生成時の掲載データを埋め込み、全件APIを再取得しない。座標不明・範囲外・撤去済みはピンにしない。住所と一覧はJavaScriptなしでも読める。
- 画像・住所・座標を本文と同じItemList/Placeに記述。タイトル・H1・説明・FAQ・内部リンクで「ふたマス」「アイマス」「設置場所」「地図」を自然に示す。URL・canonicalは維持。
- 掲載数はデータから算出。全国の全設置数や確認日を水増ししない。
- 地図は既存全国地図と同じLeaflet 1.9.4 / OpenStreetMap。タイルは表示直前に読み込む。外部地図が失敗しても静的一覧・各地図リンクは残る。

## 確認

- `python3 -m unittest apps.scraper.test_generate_character_work_pages apps.scraper.test_generate_character_manhole_page apps.scraper.test_generate_sitemap`: 104件成功。
- `node --check apps/web/assets/character-work-map.js`、`git diff --check`: 成功。
- 公開データから8ページ生成。ChromeのPC表示と390×844表示で確認。
- トップ写真が読み込める、地図10ピン、前川みくのピンから対応する一覧へ移動、横溢れなし、コンソールエラーなし。
- SEO順位の上昇は未検証。公開後にSearch Consoleで同じ関連語・期間を比較する。

## 調査時点の基準

Search Console（ドメインpokefuta.com、2026-09-02〜09-29）で「アイマス|アイドルマスター|idolmaster|ふたマス|ふたます」は51表示・1クリック。「ふたマス 一覧」が1クリック。調査時点の最新集計日は9月29日。
