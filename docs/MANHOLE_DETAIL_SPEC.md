# マンホール詳細ページ 共通仕様

data.pokefuta.com（tracker）と pokefuta.com のマンホール詳細ページを共通化するための仕様。

## 方針

- **未ログイン時の構成は tracker 側（現行の `generate_manhole_pages.py` の出力）に寄せる。**
  未ログイン訪問者の意図（場所を調べる・行く・周辺を回遊する）に合い、SEO資産もこちらにあるため。
- pokefuta.com の強みである「みんなの写真」ギャラリーと投稿CTAは共通仕様に取り込む（tracker へ逆輸入）。
- ログイン時の体験（写真図鑑・訪問記録・コメント投稿）は pokefuta.com 専用レイヤーとして共通構成の上に重ねる。tracker はログインレイヤーを持たない。

## 共通セクション構成（上から順）

| # | セクション | 内容 | 未ログイン | pokefuta.com ログイン時 |
|---|---|---|---|---|
| 1 | 戻る導線 | 全国マップ／一覧へ戻る | 共通 | 共通 |
| 2 | ヒーロー | 代表写真＋撮影者クレジット、タイトル(h1)、バッジ（レア・初期等）、タグ、統計チップ（県内枚数・30km圏内件数） | 共通 | 「あなたの写真」があればそちらを優先表示＋写真図鑑ステータス |
| 3 | みんなの写真 | 公開写真ギャラリー（代表含め最大5枚）。全量は pokefuta.com へのリンクで誘導 | 共通（**新設**） | 自分の写真バッジ付き、「別の構図を追加する」CTA |
| 4 | アクション | 「写真を投稿」（→ pokefuta.com、未ログインはログインCTA文言）／「Google Mapsで行き方を見る」 | 共通 | 投稿フォームへ直行 |
| 5 | 設置場所 | 都道府県・市区町村・施設・住所 | 共通 | 共通 |
| 6 | 登場ポケモン | 4言語名・タイプ・世代・「同じポケふたを見る」 | 共通 | 共通 |
| 7 | 次に寄れるポケふた | 距離付き近隣リスト（5件） | 共通 | 共通 |
| 8 | 同じポケモンのポケふた | 全国の同ポケモン設置 | 共通 | 共通 |
| 9 | 県内のポケふた | 同県リスト | 共通 | 共通 |
| 10 | リンク・共有 | X/LINE/Web Share、公式サイト、県マップ、全国マップ | 共通 | 共通 |
| 11 | コメント | 閲覧＋投稿 | pokefuta.com のみ（閲覧可、投稿はログイン） | pokefuta.com のみ |

- tracker は 1–10 を静的HTMLに焼き込む（現行どおり日次）。
- pokefuta.com は同じ順序・同じ見出しで描画し、11 とログインレイヤーを追加する。

## データソース対応表

| セクション | tracker 側ソース | pokefuta.com 側ソース |
|---|---|---|
| ヒーロー・ギャラリー | `docs/latest-manhole-photos.json`（拡張版）＋ `dataset/manhole/image/` | `/api/manholes/[id]`（公開写真） |
| タイトル・バッジ・タグ・設置場所 | `docs/pokefuta.ndjson` ＋ `manhole_titles.json` | `docs/api/manholes.json`（bake-app-data.yml 焼き込み） |
| 登場ポケモン | `docs/pokemon_metadata.json` ＋ `pokemon_types_bilingual.json` | 同スナップショット or 既存API |
| 近隣・同ポケモン・県内 | `docs/pokefuta.ndjson`（生成時に計算） | 同スナップショットから計算 |

## 複数写真の扱い

現行の `latest-manhole-photos.json` は 1マンホール=最新1枚。以下のとおり拡張する。

### エクスポート拡張（pokefuta repo: `tools/export_latest_manhole_photos.py`）

- `photos[manhole_id]` の既存フィールド（代表＝最新1枚）は**そのまま維持**（後方互換）。
- 各エントリに `gallery` 配列を追加：代表を含む公開写真を新しい順に**最大5枚**。

```jsonc
"photos": {
  "1": {
    "manhole_id": 1,
    "photo_id": "...",        // 代表（最新）— 従来どおり
    "url": "...",
    "...": "...",
    "gallery": [
      { "photo_id": "...", "url": "...", "storage_key": "...", "shot_at": "...", "created_at": "...", "display_name": "...", "public_user_id": "..." }
    ]
  }
}
```

- 対象は `is_public = true` の写真のみ。撮影者名のキーは既存の代表写真と同じ `display_name`（app_user の display_name を引く）。
- 代表・`gallery` の各エントリに `public_user_id`（app_user.id の公開UUID）を含める。投稿者の公開スタンプ帳 `pokefuta.com/users/{public_user_id}/visits` へのリンク生成に使う。

### 取り込み拡張（tracker repo: `apps/tools/import_latest_manhole_photos.py`）

- 代表: 現行どおり `dataset/manhole/image/{id}_latest.jpeg`。
- ギャラリー: `dataset/manhole/image/{id}_{photo_idの先頭8桁(hex)}.jpeg`。代表と重複する photo_id はスキップ。既存ファイルは再ダウンロードしない（冪等）。
- **リポジトリ肥大対策**: ギャラリー画像も代表と同じスクエア720px・JPEG品質82に縮小して保存。エクスポートから外れた photo_id のファイルは自動削除（`--limit` 指定時は削除しない）。

### ページ生成（tracker repo: `generate_manhole_pages.py`）

- `gallery` が2枚以上のときのみセクション3を描画。代表をヒーロー、残りをサムネイルグリッド。
- 末尾に「すべての写真を見る → pokefuta.com/manhole/{id}」リンク。
- `gallery` 未定義・1枚以下は現行と同じ見た目（後方互換）。
- 撮影者クレジット（ヒーロー・ギャラリー共通）: `public_user_id` が有効なUUIDのとき `📷 表示名` を `pokefuta.com/users/{public_user_id}/visits` へのリンク（`.poster-link`）にする。無効・欠落時は従来どおりテキスト表示。
- セクション10（リンク）に「ポケふた写真館」カードを常設し `pokefuta.com/manhole/{id}` へ飛ばす（ギャラリー非表示のふたにも写真館導線を確保）。

## 実装ステップ

1. **pokefuta repo**: `tools/export_latest_manhole_photos.py` に `gallery` 追加（後方互換）
2. **tracker repo**: `apps/tools/import_latest_manhole_photos.py` のギャラリーDL＋縮小＋掃除
3. **tracker repo**: `generate_manhole_pages.py` にギャラリーセクション追加
4. **pokefuta repo**: `ManholePage.tsx` の未ログイン時レイアウトを本仕様のセクション順に再構成（近隣・同ポケモン・県内セクションの新設を含む）
5. `.claude/commands/import-photos.md` の手順・確認事項を更新

1〜3 と 4 は独立して進められる。1→2→3 の順でデータから先に通す。
