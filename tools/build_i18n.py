#!/usr/bin/env python3
"""Build multilingual index.html files from index.template.html + i18n strings.

Usage:
  python tools/build_i18n.py              # build all 4 languages
  python tools/build_i18n.py en           # build English only
  python tools/build_i18n.py en zh-TW     # build multiple
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
TEMPLATE = ROOT / 'apps' / 'web' / 'index.template.html'
I18N_DIR = ROOT / 'apps' / 'web' / 'i18n'
PREF_FILE = ROOT / 'apps' / 'web' / 'i18n' / 'prefectures.json'
DIST = ROOT / 'dist'

LANGS = ['en', 'zh-TW', 'zh-CN', 'ko']


def build(lang: str) -> None:
    strings_path = I18N_DIR / f'strings.{lang}.json'
    if not strings_path.exists():
        print(f'[SKIP] {strings_path} not found')
        return

    template = TEMPLATE.read_text(encoding='utf-8')
    strings: dict = json.loads(strings_path.read_text(encoding='utf-8'))

    if not PREF_FILE.exists():
        print(f'[ERROR] Required file not found: {PREF_FILE}')
        sys.exit(1)
    pref_data = json.loads(PREF_FILE.read_text(encoding='utf-8'))
    strings['PREFECTURE_NAMES_JSON'] = json.dumps(pref_data, ensure_ascii=False).replace('</', '<\\/')

    result = template
    for key, value in strings.items():
        if isinstance(value, (dict, list)):
            # Serialize nested objects to JSON (used for I18N_OBJECT injection)
            safe_json = json.dumps(value, ensure_ascii=False).replace('</', '<\\/')
            result = result.replace(f'%%{key}%%', safe_json)
        else:
            result = result.replace(f'%%{key}%%', str(value))

    out = DIST / lang / 'index.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result, encoding='utf-8')
    print(f'[OK]  dist/{lang}/index.html ({len(result):,} bytes)')

    # Warn about any unreplaced markers
    import re
    remaining = re.findall(r'%%\w+%%', result)
    if remaining:
        unique = sorted(set(remaining))
        print(f'  [WARN] unreplaced markers: {unique}')


def main() -> None:
    if not TEMPLATE.exists():
        print(f'[ERROR] Template not found: {TEMPLATE}')
        print('  Run: python tools/make_template.py')
        sys.exit(1)

    targets = sys.argv[1:] if len(sys.argv) > 1 else LANGS
    for lang in targets:
        build(lang)


if __name__ == '__main__':
    main()
