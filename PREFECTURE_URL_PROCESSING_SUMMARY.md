# 都道府県ページURL置換 - 処理完了

## 処理概要

ポケモンマンホールデータの都道府県主体ページURL処理が完了しました。

### 処理フロー

1. **クリーニング**: `pokemons`から「ローカルActs{県}ページへ」を抽出
2. **フラグ追加**: `is_prefecture_site`フラグを設定
3. **URL置換**: テキスト表記を実URLに変換

## 処理結果

### 対象データ
- **総レコード数**: 470
- **クリーニング対象**: 323件 (68.7%)
- **都道府県種別**: 12都道府県

### 都道府県別集計

| 都道府県 | マンホール件数 | URL |
|---------|--------|-----|
| 北海道 | 50 | https://local.pokemon.jp/municipality/hokkaido/ |
| 福島県 | 43 | https://local.pokemon.jp/municipality/fukushima/ |
| 宮城県 | 37 | https://local.pokemon.jp/municipality/miyagi/ |
| 岩手県 | 36 | https://local.pokemon.jp/municipality/iwate/ |
| 三重県 | 31 | https://local.pokemon.jp/municipality/mie/ |
| 宮崎県 | 26 | https://local.pokemon.jp/municipality/miyazaki/ |
| 鳥取県 | 20 | https://local.pokemon.jp/municipality/tottori/ |
| 高知県 | 18 | https://local.pokemon.jp/municipality/kochi/ |
| 香川県 | 18 | https://local.pokemon.jp/municipality/kagawa/ |
| 福井県 | 17 | https://local.pokemon.jp/municipality/fukui/ |
| 沖縄県 | 17 | https://local.pokemon.jp/municipality/okinawa/ |
| 長崎県 | 10 | https://local.pokemon.jp/municipality/nagasaki/ |

## データの変換例

### Before（処理前）
```json
{
  "id": "10",
  "prefecture": "岩手県",
  "pokemons": ["カブト", "ローカルActs岩手県ページへ"],
  "prefecture_site_url": "",
  "is_prefecture_site": false
}
```

### After（処理後）
```json
{
  "id": "10",
  "prefecture": "岩手県",
  "pokemons": ["カブト"],
  "prefecture_site_url": "https://local.pokemon.jp/municipality/iwate/",
  "is_prefecture_site": true
}
```

## 出力ファイル

- **ファイル名**: `pokefuta_with_urls.ndjson`
- **レコード数**: 470
- **サイズ**: 259KB
- **都道府県URLが置換された件数**: 323件

## 実装ファイル一覧

| ファイル | 説明 |
|---------|------|
| `clean_prefecture_urls.py` | pokemons からURL抽出・クリーニング |
| `prefecture_url_mapping.py` | URL対応表（テキスト表記 → 実URL） |
| `replace_prefecture_urls.py` | テキスト表記を実URLに置換 |
| `docs/PREFECTURE_CLEANING.md` | 詳細ドキュメント |
| `schema/database.sql` | スキーマ更新（フィールド追加） |

## 処理成功メトリクス

| 項目 | 結果 |
|-----|------|
| 正常に置換 | 323件 ✓ |
| 処理スキップ | 147件 |
| エラー | 0件 |
| **成功率** | **100%** |

---

**処理完了日**: 2026年5月9日  
**ステータス**: ✅ 完了
