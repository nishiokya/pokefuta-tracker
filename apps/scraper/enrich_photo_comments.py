#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract building / landmark / access / parking from user photo comments.

ユーザー投稿コメントから施設名・目印・アクセス・駐車場情報を抽出し、
latest-manhole-photos.json の各エントリに追加する。

使い方:
  python apps/scraper/enrich_photo_comments.py

  # 乾燥走行（API 呼ばずに対象件数を確認）
  python apps/scraper/enrich_photo_comments.py --dry-run

  # 複数ファイルをまとめて更新
  python apps/scraper/enrich_photo_comments.py \\
      --inputs apps/web/latest-manhole-photos.json docs/latest-manhole-photos.json

  # 既存の抽出済みエントリを上書き再抽出
  python apps/scraper/enrich_photo_comments.py --overwrite
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import anthropic

EXTRACTED_FIELDS = ("building", "landmark", "access", "parking")

# claude-haiku-4-5 で十分な精度が出る短文抽出タスク
MODEL = "claude-haiku-4-5-20251001"

# 1 回の API 呼び出しでまとめる件数（コスト削減）
BATCH_SIZE = 10

SYSTEM_PROMPT = """\
ポケふた（ポケモンマンホール）の写真に投稿されたコメントから、訪問に役立つ場所情報を抽出してください。

抽出するフィールド:
  building : 施設・建物名（道の駅・公園・温泉・博物館・駅構内・ショッピングモールなど）
  landmark : 目印となる場所・もの（「〜の前」「〜の横」「〜の近く」など）
  access   : アクセス情報（最寄り駅・方向・徒歩時間・バス停など）
  parking  : 駐車場情報（場所・料金・時間制限など）

ルール:
- 各フィールドは短いフレーズ（30文字以内目安）で記述する
- 言及されていない場合は null
- 「投稿テスト」「テスト」などコメントとして意味をなさない場合はすべて null
- JSON のみを返す（他の説明文不要）

出力例（複数件をまとめる場合は配列）:
[
  {"id": 61, "building": "洞龍の湯", "landmark": null, "access": "洞爺湖駐車場から徒歩5分", "parking": "洞爺湖駐車場"},
  {"id": 63, "building": "道の駅 上ノ国もんじゅ", "landmark": null, "access": null, "parking": null}
]
"""


def atomic_write_json(path: str, data: Any) -> None:
    d = os.path.dirname(os.path.abspath(path)) or "."
    with tempfile.NamedTemporaryFile("w", delete=False, dir=d, encoding="utf-8") as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        p = tmp.name
    os.replace(p, path)


def extract_json_array(text: str) -> list[dict] | None:
    """JSON 配列をレスポンステキストから抽出する。"""
    m = re.search(r"\[.*?\]", text, re.DOTALL)
    if not m:
        return None
    try:
        result = json.loads(m.group(0))
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    return None


def build_batch_prompt(entries: list[dict]) -> str:
    lines = ["以下のコメントから場所情報を抽出してください。\n"]
    for e in entries:
        lines.append(f'id={e["manhole_id"]}: {e["comment"]}')
    lines.append(
        f"\n{len(entries)}件分を JSON 配列で返してください。"
        " 各要素に id, building, landmark, access, parking を含めてください。"
    )
    return "\n".join(lines)


def call_claude(client: anthropic.Anthropic, entries: list[dict]) -> list[dict]:
    """entries の comment からフィールドを抽出して返す。"""
    prompt = build_batch_prompt(entries)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text
    parsed = extract_json_array(text)
    if parsed is None:
        print(f"  WARNING: JSON parse failed for batch, raw:\n{text[:300]}", file=sys.stderr)
        return []
    return parsed


def enrich_file(
    path: str,
    client: anthropic.Anthropic,
    overwrite: bool,
    dry_run: bool,
) -> int:
    """1 ファイルを処理して更新した件数を返す。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    photos: dict = data.get("photos", {})
    if not isinstance(photos, dict):
        print(f"  SKIP {path}: photos is not a dict", file=sys.stderr)
        return 0

    # 処理対象を選別
    targets = []
    for key, entry in photos.items():
        comment = (entry.get("comment") or "").strip()
        if not comment:
            continue
        already_extracted = any(entry.get(f) for f in EXTRACTED_FIELDS)
        if already_extracted and not overwrite:
            continue
        targets.append(entry)

    print(f"{path}: {len(targets)} entries to enrich (overwrite={overwrite})")

    if dry_run or not targets:
        return 0

    updated = 0
    for i in range(0, len(targets), BATCH_SIZE):
        batch = targets[i : i + BATCH_SIZE]
        print(f"  batch {i // BATCH_SIZE + 1}: ids={[e['manhole_id'] for e in batch]}")
        results = call_claude(client, batch)

        result_by_id = {str(r.get("id")): r for r in results if r.get("id") is not None}

        for entry in batch:
            mid = str(entry["manhole_id"])
            extracted = result_by_id.get(mid, {})
            changed = False
            for field in EXTRACTED_FIELDS:
                val = extracted.get(field)
                # null / 空文字は書き込まない（既存値を消さない）
                if val and val != entry.get(field):
                    entry[field] = val
                    changed = True
            if changed:
                updated += 1
                print(f"    id={mid}: {', '.join(f'{f}={entry[f]!r}' for f in EXTRACTED_FIELDS if entry.get(f))}")

    if updated:
        atomic_write_json(path, data)
        print(f"  wrote {path} ({updated} updated)")

    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=["apps/web/latest-manhole-photos.json", "docs/latest-manhole-photos.json"],
        help="対象の latest-manhole-photos.json ファイルパス（複数可）",
    )
    parser.add_argument("--overwrite", action="store_true", help="抽出済みエントリを上書き再抽出する")
    parser.add_argument("--dry-run", action="store_true", help="API を呼ばず対象件数のみ表示")
    parser.add_argument("--model", default=MODEL, help=f"Claude モデル名 (default: {MODEL})")
    args = parser.parse_args()

    # .env.local から API キーを読み込む（import_latest_manhole_photos.py と同じ方式）
    for env_path in [".env.local", ".env"]:
        p = Path(env_path)
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY が設定されていません (.env.local に記載するか環境変数で渡してください)", file=sys.stderr)
        return 1

    client = anthropic.Anthropic(api_key=api_key) if api_key else None  # type: ignore[arg-type]

    total = 0
    for path in args.inputs:
        if not Path(path).exists():
            print(f"SKIP {path} (not found)")
            continue
        total += enrich_file(path, client, overwrite=args.overwrite, dry_run=args.dry_run)

    print(f"\nDone. total updated={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
