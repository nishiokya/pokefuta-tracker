# ガンダム作品ガイドの投稿写真

`/characters/gundam/` は `canonical_ref` で結びついた公開投稿から各蓋の最新写真を選ぶ。
ギャラリー・Hero・設置エリア・地図ピンは同じ投稿の写真を使う。

## 切り抜き

`dataset/design_manhole_lids.json` は公開投稿ID → `{box: [x0,y0,x1,y1], width, height}`。
boxは表示方向に対する0〜1の範囲。CSSで蓋の楕円を切り抜き、縦横比は維持する。
写真の複製・生成・本番DBの変更は行わない。元画像の公開エンドポイントを使う。
投稿の変更時に別の写真の枠を流用しない。未検出は元写真を表示する。
「ふただけ表示」で切り抜きと元写真を切り替えられる。

K11の既存モデルで更新（モデル再学習不要）:

```sh
/home/tako/projects/manhole-score/.venv/bin/python apps/tools/detect_design_manhole_lids.py \
  --submissions docs/design_manholes.ndjson \
  --detector-root /home/tako/projects/manhole-score \
  --output dataset/design_manhole_lids.json
```

検出結果は必ず目視確認してからコミットする。新しい投稿IDだけを検出するため、
再検出するIDは作業コピーの台帳から取り除く。台帳の変更もPagesのビルド対象。

## 投稿者

`character-work-photos.js` は既存のSupabaseクライアントを使い、ページの投稿IDだけを
`design_manhole` の `status=published` で絞り、公開カラム `id,submitter_name` だけ読む。
匿名で利用できる既存の公開権限を使い、権限やRLSは変更しない。
200件の一覧APIに依存しないため、古い投稿でも名前が表示される。
名前は `textContent` で挿入する。未設定・取得失敗時は「写真館の投稿」と表示し投稿詳細へのリンクを残す。
名前やauth UIDを静的データ・HTML・コミットへ持ち込まない。
