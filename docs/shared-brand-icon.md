# 共通ブランドアイコン

2026-10-11 採用: 「立てたふた＋白いカメラ」。赤白の格子入りマンホールを背面に、大きな白いカメラを手前に重ねる。

外枠は太い白（`#FFFDF4`）。赤白の上下分割による公式との誤認について検討中のため、PRはDraft。配色の最終判断までマージしない。

- `apps/web/assets/brand-icon.svg` は写真館の `public/brand-icon.svg` と同一。変更時は両サイトを更新する。
- ヘッダーマークとfaviconは `inject_site_header.py` で全生成ページ・全言語に反映する。旧favicon指定を置き換える。
- 配信用の正本は `apps/web/assets/`。Pagesビルドで `dist/assets/` とルートのfaviconフォールバックへコピーする。
- faviconは16/32/48pxのICO、48/96pxのPNG、SVG。ホーム画面用は180px。
- OGP・地図マーカーは変更しない。
