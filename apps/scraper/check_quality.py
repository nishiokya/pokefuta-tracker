#!/usr/bin/env python3
import json

good = fallback = suspicious = 0
with open('pokefuta.ndjson') as f:
    for line in f:
        r = json.loads(line)
        a = r.get('address', '')
        if not a: 
            suspicious += 1
        elif a.startswith(('県/', '道/')): 
            fallback += 1
        elif len(a) < 5: 
            suspicious += 1
        else: 
            good += 1

print(f"✓ Complete addresses: {good}/470")
print(f"❌ Fallback only: {fallback}")
print(f"⚠  Suspicious: {suspicious}")
print(f"\n✅ Quality Score: {good/470*100:.1f}%")
