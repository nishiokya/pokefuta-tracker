#!/usr/bin/env python3
"""Build multilingual HTML files from template + i18n strings.

Processes index.template.html → dist/{lang}/index.html
         map.template.html   → dist/{lang}/map.html

Usage:
  python tools/build_i18n.py              # build all 4 languages
  python tools/build_i18n.py en           # build English only
  python tools/build_i18n.py en zh-TW     # build multiple
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
I18N_DIR = ROOT / 'apps' / 'web' / 'i18n'
PREF_FILE = ROOT / 'apps' / 'web' / 'i18n' / 'prefectures.json'
DIST = ROOT / 'dist'

LANGS = ['en', 'zh-TW', 'zh-CN', 'ko']

# Each entry: (template path, output filename)
TEMPLATES = [
    (ROOT / 'apps' / 'web' / 'index.template.html', 'index.html'),
    (ROOT / 'apps' / 'web' / 'map.template.html',   'map.html'),
]


def build_template(template_path: pathlib.Path, out_name: str, lang: str, strings: dict, pref_data) -> None:
    if not template_path.exists():
        print(f'[SKIP] Template not found: {template_path}')
        return

    template = template_path.read_text(encoding='utf-8')
    merged = dict(strings)
    merged['PREFECTURE_NAMES_JSON'] = json.dumps(pref_data, ensure_ascii=False).replace('</', '<\\/')

    result = template
    for key, value in merged.items():
        if isinstance(value, (dict, list)):
            safe_json = json.dumps(value, ensure_ascii=False).replace('</', '<\\/')
            result = result.replace(f'%%{key}%%', safe_json)
        else:
            result = result.replace(f'%%{key}%%', str(value))

    out = DIST / lang / out_name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result, encoding='utf-8')
    print(f'[OK]  dist/{lang}/{out_name} ({len(result):,} bytes)')

    import re
    remaining = re.findall(r'%%\w+%%', result)
    if remaining:
        unique = sorted(set(remaining))
        print(f'  [WARN] unreplaced markers: {unique}')


def build(lang: str) -> None:
    strings_path = I18N_DIR / f'strings.{lang}.json'
    if not strings_path.exists():
        print(f'[SKIP] {strings_path} not found')
        return

    strings: dict = json.loads(strings_path.read_text(encoding='utf-8'))

    if not PREF_FILE.exists():
        print(f'[ERROR] Required file not found: {PREF_FILE}')
        sys.exit(1)
    pref_data = json.loads(PREF_FILE.read_text(encoding='utf-8'))

    for template_path, out_name in TEMPLATES:
        build_template(template_path, out_name, lang, strings, pref_data)


def main() -> None:
    index_template = ROOT / 'apps' / 'web' / 'index.template.html'
    if not index_template.exists():
        print(f'[ERROR] Template not found: {index_template}')
        print('  Run: python tools/make_template.py')
        sys.exit(1)

    targets = sys.argv[1:] if len(sys.argv) > 1 else LANGS
    for lang in targets:
        build(lang)


if __name__ == '__main__':
    main()
