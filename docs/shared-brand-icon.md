# 共通ブランドアイコン

2026-10-11 採用: 「立てたふた＋白い図鑑」。赤白の面と茶色の格子のマンホールを背面に、白い見開きの本を手前に重ねる。

ふたの上半分は赤（`#DA3943`）、下半分は白（`#FFF5DE`）。格子線と外枠は茶色（`#66363C`）。白い本は見開きと背表紙で図鑑を表す。全体を枠いっぱいに配置する。

本はふたの手前に重ね、白い下半分の露出を減らす。

- `apps/web/assets/brand-icon.svg` は図鑑の本マーク。写真館の `public/brand-icon.svg` はカメラマーク。ふたの形と配色は共通にする。
- ヘッダー（30px）は `apps/web/assets/brand-mark.svg`、faviconは `brand-icon.svg`。`brand-mark.svg` は `brand-icon.svg` と同じ絵で、30px表示用に輪郭線を太くし、viewBoxを内容に合わせて詰め、ふたの下半分を背景に溶けない `#F6E6C4` にしたもの（48pxの線のまま縮めると0.8px程度になってにじむため）。絵の形・配置は変えない。
- ヘッダーマークとfaviconは `inject_site_header.py` で全生成ページ・全言語に反映する。旧favicon指定を置き換える。
- 配信用の正本は `apps/web/assets/`。Pagesビルドで `dist/assets/` とルートのfaviconフォールバックへコピーする。
- faviconは16/32/48pxのICO、48/96pxのPNG、SVG。ホーム画面用は180px。
- Apple用180pxは全面不透明な `#FFF5DE` のキャンバスへ合成する。書き出し後に180×180pxと透明画素ゼロを確認する。
- OGP・地図マーカーは変更しない。
