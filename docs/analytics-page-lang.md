# 言語版の計測（page_lang）

翻訳版（`/en/` `/zh-TW/` `/zh-CN/` `/ko/`）のトップ・地図は日本語版と同じ `page_path`（`/top`, `/map` …）を送る。言語版は `page_path` ではなく、`apps/web/assets/analytics.js` が URL から決める `page_lang` で分ける。`page_path` を言語ごとに変えると、`/top` を前後で比べる評価（PCトップのヒーロー導線など）が崩れるため。

| パラメータ | 値 | 付くもの |
| --- | --- | --- |
| page_lang | `ja` / `en` / `zh-TW` / `zh-CN` / `ko`（URL の先頭のフォルダ。それ以外は `ja`） | page_view とすべてのカスタムイベント |

GA4 の `language` はブラウザの言語で、表示している言語版とは別物。

## 登録（公開前に済ませる）

GA4 プロパティ 507799028 の「管理 → カスタム定義 → カスタムディメンションを作成」で、次のとおり登録する。登録より前のデータは探索へさかのぼって入らないので、**この計測を本番に出す前に登録する**。

| 項目 | 値 |
| --- | --- |
| ディメンション名 | page_lang |
| 範囲 | イベント |
| イベントパラメータ | page_lang |

登録できたかは、Data API の `properties/507799028/metadata` に `customEvent:page_lang` が出るかで確かめる。

- 登録日: 未登録

登録より前の期間は `pageLocation`（URL 全体）で言語版を分ける。
