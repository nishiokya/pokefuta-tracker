# SEO実装記録：HTTPS転送と千葉ページ

実施日：2026-10-04（JST）

HTTPS転送は本番反映済み。千葉ページは実装・ローカル検証済みで、PRレビュー・マージ後に公開する段階です。技術設定と内容改善は別の変更として記録します。

## 1. HTTPS転送：本番反映済み

対象：`nishiokya/pokefuta-tracker` のGitHub Pages、`data.pokefuta.com`。

- 原因：Pagesの `https_enforced` がfalse。証明書はapproved、有効期限2026-11-14。
- 対応：GitHub Pages設定の `https_enforced` だけをtrueに変更。ドメイン・デプロイ方式は変更なし。
- 設定確認：`html_url` が `https://data.pokefuta.com/`、`https_enforced: true`。
- 確認日時：**2026-10-04 14:28 JST**。以下のHTTP URLがすべて同じパス・クエリのHTTPS URLへ301転送。

| パス | HTTP | Location |
|---|---|---|
| `/` | 301 | `https://data.pokefuta.com/` |
| `/prefectures/chiba/` | 301 | `https://data.pokefuta.com/prefectures/chiba/` |
| `/manholes/222/` | 301 | `https://data.pokefuta.com/manholes/222/` |
| `/character_manholes.html` | 301 | `https://data.pokefuta.com/character_manholes.html` |
| `/map.html?pref=%E5%8D%83%E8%91%89%E7%9C%8C` | 301 | 同じクエリを維持したHTTPS URL |

上記のHTTPS側は14:26 JSTにすべて200を確認しました。キャラクターマンホールページのみ一時的に古い200応答がCDNに残りましたが、キャッシュ更新後の14:28には301へ切り替わったことを確認しています。

設定はGit管理外です。コードをrevertしても転送設定は戻りません。運用上の問題が発生した場合の戻し方はPages設定の「Enforce HTTPS」を無効化する操作です。今回のサンプルでは問題は発生していません。

仕様の根拠：[GitHub Pages REST API](https://docs.github.com/en/rest/pages/pages#update-information-about-a-github-pages-site)。

## 2. 千葉ページ：実装・検証済み、未デプロイ

対象：[千葉ページ](https://data.pokefuta.com/prefectures/chiba/)。実装ブランチ：`codex/chiba-seo-https`。最新mainの `99e9e9d` から分離して実装し、元の作業フォルダにある別作業の変更は含めていません。

### 内容

- タイトルを「千葉のポケふた4枚はどこ？香取市・佐原の場所一覧と地図」へ変更。枚数はデータから生成。
- H1・meta description・OGP・構造化データに共通のタイトル・説明を使用。
- 地図より前に、佐原駅前・伊能忠敬記念館・水の郷さわら・水郷佐原あやめパークの場所一覧を表示。
- 場所名・住所は既存データを利用。各リンクは同じページの対応するマンホールカードへ移動。
- 「電車・徒歩」「車」の案内を追加。記念館への徒歩15分は香取市の公式案内が根拠。4地点すべてを駅前の徒歩コースと誤認させない説明を追加。
- 公式出典4件と確認日2026-10-04を表示。
- ガイドを `dataset/prefecture_visit_guides.json` に分離し、手動更新できるようにした。参照先のいずれかが削除・非アクティブ・設置前ならガイド全体を表示せず、既存の自治体案内へ戻る。
- 地図・写真・詳細・写真館への既存導線を維持。新しいリンクも共通GA4を使い、`surface=visit_guide` で区別。内部UTMは追加していない。
- 新しい手動データの更新をPagesデプロイの起動条件へ追加。既存ワークフローで県ページのテストを実行する構成を維持。

### 根拠

- [香取市：ポケふた設置場所](https://www.city.katori.lg.jp/sightseeing/meisho/kanko/pokefuta.html)
- [香取市：伊能忠敬記念館のアクセス・駐車案内](https://www.city.katori.lg.jp/sightseeing/museum/guide.html)
- [香取市：水郷佐原あやめパーク](https://www.city.katori.lg.jp/sightseeing/ayamepark/index.html)
- [香取市：水の郷さわら](https://www.city.katori.lg.jp/nogyo_sangyo/koryu/s_mizunosato.html)

徒歩15分以外の移動時間、バス時刻、施設の営業時間は推測で追加していません。周遊の組み立て方は編集上の提案です。

### 検証

- `test_generate_prefecture_pages`、`test_prefectures`、`test_web_prefecture_links`、`test_analytics_contract`、`test_css_grid_tracks`、`test_generate_sitemap`：**計118件成功**。
- 追加した検証：ガイドの本番生成経路、全4地点のアンカーの存在と一意性、他県への混入防止、参照地点の削除・設置前・非アクティブ時の非表示、HTMLエスケープと非HTTPS出典の除外。
- 実際の生成コマンドで47県と県一覧を出力し、共通ヘッダーを適用。
- ChromeでPC幅1623pxとスマートフォン幅390pxを確認。どちらも横にはみ出しなし。
- スマートフォンのスクリーンショットで4地点・住所・回り方の表示を確認。
- 佐原駅前リンクを実際にクリックし `#manhole-222` への移動と対象表示を確認。
- `git diff --check` 成功。

## 公開後の確認・測定

千葉の公開日はPRマージ後のPagesデプロイ成功日時を記録し、HTTPS設定変更日時と区別すること。公開後にページのタイトル・ガイド・アンカー・canonicalを確認する。

SEOの基準値はSearch Consoleの2026-09-02～09-29：千葉ページ42クリック・4,125表示・CTR1.0%・平均順位6.8。今回の実装だけで成果が出たとは判断せず、再クロール後の28日間と比較する。

検索語×ページ、国、デバイスを揃え、千葉・香取・佐原の語群のクリック・表示・CTR・順位を確認する。図鑑内での地点・地図利用は `surface=visit_guide` で分ける。県別流入や写真投稿までの分析は、写真館側で既存の県パラメータをGA4へ引き継いでいることを別途確認する。

京都・大阪・北海道の既存SEO施策、写真館側のwww統一・CLS改善・Soft 404対策は、この変更には含めていません。
