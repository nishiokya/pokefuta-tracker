#!/usr/bin/env python3
from pathlib import Path
import json

_candidates = [
    Path(__file__).parent.parent / 'scraper' / 'pokefuta.ndjson',
    Path(__file__).parent.parent.parent / 'docs' / 'pokefuta.ndjson',
]
DATA = next((p for p in _candidates if p.exists()), _candidates[-1])

good = fallback = suspicious = total = 0
with open(DATA) as f:
    for line in f:
        r = json.loads(line)
        a = r.get('address', '')
        total += 1
        if not a:
            suspicious += 1
        elif a.startswith(('県/', '道/')):
            fallback += 1
        elif len(a) < 5:
            suspicious += 1
        else:
            good += 1

print(f"✓ Complete addresses: {good}/{total}")
print(f"❌ Fallback only: {fallback}")
print(f"⚠  Suspicious: {suspicious}")
print(f"\n✅ Quality Score: {good/total*100:.1f}%")
