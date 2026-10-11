# 共通ブランドアイコン

2026-10-11 採用: 「立てたふた＋白いカメラ」。赤白の格子入りマンホールを背面に、大きな白いカメラを手前に重ねる。

内側の格子線は太い白（`#FFFDF4`）、外枠は茶色の細い縁。白いカメラは初稿から約10%縮小。配色は赤白で確定。

カメラは上寄せにして、ふたの白い下半分の露出を減らす。

- `apps/web/assets/brand-icon.svg` は写真館の `public/brand-icon.svg` と同一。変更時は両サイトを更新する。
- ヘッダーマークとfaviconは `inject_site_header.py` で全生成ページ・全言語に反映する。旧favicon指定を置き換える。
- 配信用の正本は `apps/web/assets/`。Pagesビルドで `dist/assets/` とルートのfaviconフォールバックへコピーする。
- faviconは16/32/48pxのICO、48/96pxのPNG、SVG。ホーム画面用は180px。
- OGP・地図マーカーは変更しない。
