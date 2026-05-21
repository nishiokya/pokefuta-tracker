#!/usr/bin/env python3
"""Compare two pokefuta NDJSON files and report change categories."""
import json
import sys

TIMESTAMP_FIELDS = {"last_updated", "first_seen", "added_at"}
CONTENT_FIELDS = {
    "pokemons", "tags", "titles", "address", "lat", "lng", "status",
    "building", "city_url", "prefecture_site_url", "is_prefecture_site",
    "city", "prefecture", "title",
}


def load_ndjson(path):
    records = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                records[str(rec["id"])] = rec
    return records


def changed_content_fields(old, new):
    return sorted(k for k in CONTENT_FIELDS if old.get(k) != new.get(k))


def analyze(base_path, head_path):
    base = load_ndjson(base_path)
    head = load_ndjson(head_path)

    new_ids, deleted_ids, ts_only_ids, content_changed = [], [], [], []

    for rid in sorted(set(base) | set(head), key=lambda x: int(x) if x.isdigit() else x):
        if rid in head and rid not in base:
            new_ids.append(rid)
        elif rid in base and rid not in head:
            deleted_ids.append(rid)
        else:
            if base[rid] == head[rid]:
                continue  # 完全一致はスキップ
            changed = changed_content_fields(base[rid], head[rid])
            if changed:
                content_changed.append((rid, changed))
            else:
                ts_only_ids.append(rid)

    return {
        "new": new_ids,
        "deleted": deleted_ids,
        "timestamp_only": ts_only_ids,
        "content_changed": content_changed,
    }, base, head


def report(results, base, head):
    lines = ["## データセット差分レポート\n"]

    total = len(results["new"]) + len(results["deleted"]) + len(results["timestamp_only"]) + len(results["content_changed"])
    lines.append(f"変更レコード数: **{total}**\n")

    if results["new"]:
        lines.append(f"### 新規追加 ({len(results['new'])} 件)")
        for rid in results["new"]:
            r = head[rid]
            lines.append(f"- id {rid}: {r.get('prefecture', '')}/{r.get('city', '')} — {', '.join(r.get('pokemons', []))}")

    if results["deleted"]:
        lines.append(f"\n### 削除 ({len(results['deleted'])} 件)")
        for rid in results["deleted"]:
            r = base[rid]
            lines.append(f"- id {rid}: {r.get('prefecture', '')}/{r.get('city', '')} — {', '.join(r.get('pokemons', []))}")

    if results["content_changed"]:
        lines.append(f"\n### コンテンツ変更 ({len(results['content_changed'])} 件) ⚠️ 要確認")
        for rid, fields in results["content_changed"]:
            r = head[rid]
            lines.append(f"- id {rid}: {r.get('prefecture', '')}/{r.get('city', '')} — 変更フィールド: `{'`, `'.join(fields)}`")

    if results["timestamp_only"]:
        ids_str = ", ".join(results["timestamp_only"][:20])
        suffix = f" … 他 {len(results['timestamp_only']) - 20} 件" if len(results["timestamp_only"]) > 20 else ""
        lines.append(f"\n### タイムスタンプのみ更新 ({len(results['timestamp_only'])} 件) — 通常の日次更新")
        lines.append(f"id: {ids_str}{suffix}")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <base.ndjson> <head.ndjson>", file=sys.stderr)
        sys.exit(2)

    results, base, head = analyze(sys.argv[1], sys.argv[2])
    print(report(results, base, head))

    if results["content_changed"]:
        sys.exit(1)
