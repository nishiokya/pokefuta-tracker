#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test noise filtering improvements"""
import re

# 改善版: 厳格なノイズキーワードフィルタリング
def extract_address_improved(html_text):
    """厳格なノイズフィルタリング - クリティカルノイズのみ除外"""
    address_patterns = [
        r'([^。\n]*(?:県|府|道|都)[^。\n]*(?:市|区|町|村)[^。\n]*(?:\d+[-−‐]\d+[-−‐]\d+|\d+[-−‐]\d+|\d+丁目|\d+番地|\d+号|\d+番)[^。\n]*)',
        r'([^。\n]*(?:市|区|町|村)[^。\n]*(?:\d+[-−‐]\d+[-−‐]\d+|\d+[-−‐]\d+|\d+丁目|\d+番地|\d+号|\d+番)[^。\n]*)',
        r'([^。\n]*(?:県|府|道|都)[^。\n]*(?:市|区|町|村)[^。、\n]*)',
    ]
    
    critical_noise = ['｜', 'ポケモン', 'マンホール', 'ポケふた']
    
    for pattern in address_patterns:
        matches = re.findall(pattern, html_text)
        if matches:
            # クリティカルノイズをチェック
            for candidate in matches:
                candidate = candidate.strip()
                if not any(keyword in candidate for keyword in critical_noise):
                    return candidate
    
    return ""

# 旧版: 最長マッチのみ
def extract_address_old(html_text):
    """旧版: 最長マッチのみ"""
    address_patterns = [
        r'([^。\n]*(?:県|府|道|都)[^。\n]*(?:市|区|町|村)[^。\n]*(?:\d+[-−‐]\d+[-−‐]\d+|\d+[-−‐]\d+|\d+丁目|\d+番地|\d+号|\d+番)[^。\n]*)',
        r'([^。\n]*(?:市|区|町|村)[^。\n]*(?:\d+[-−‐]\d+[-−‐]\d+|\d+[-−‐]\d+|\d+丁目|\d+番地|\d+号|\d+番)[^。\n]*)',
        r'([^。\n]*(?:県|府|道|都)[^。\n]*(?:市|区|町|村)[^。、\n]*)',
    ]
    
    for pattern in address_patterns:
        matches = re.findall(pattern, html_text)
        if matches:
            return max(matches, key=len).strip()
    
    return ""

# テストケース
test_cases = [
    {
        "id": 49,
        "html": "宮城県/松島町｜ポケモンマンホール『ポケふた』周辺",
        "expected_old": "宮城県/松島町｜ポケモンマンホール『ポケふた』周辺",
        "expected_improved": ""
    },
    {
        "id": "valid",
        "html": "宮城県松島町磯崎字浜1番地\n付近\nポケモンセンター",
        "expected_old": "宮城県松島町磯崎字浜1番地",
        "expected_improved": "宮城県松島町磯崎字浜1番地"
    },
    {
        "id": "with_noise1",
        "html": "東京都渋谷区\n道玄坂2-25-12｜ポケモン",
        "expected_old": "東京都渋谷区\n道玄坂2-25-12｜ポケモン",
        "expected_improved": ""
    },
    {
        "id": "with_noise2",
        "html": "大阪府大阪市北区中之島3丁目 マンホール周辺",
        "expected_old": "大阪府大阪市北区中之島3丁目 マンホール周辺",
        "expected_improved": "大阪府大阪市北区中之島3丁目"
    },
]

print("=" * 60)
print("ノイズフィルタリング改善テスト")
print("=" * 60)

for test in test_cases:
    test_id = test["id"]
    html = test["html"]
    old_result = extract_address_old(html)
    improved_result = extract_address_improved(html)
    
    print(f"\n【テスト {test_id}】")
    print(f"HTML: {html[:60]}...")
    print(f"旧版結果:  {old_result}")
    print(f"改善版:    {improved_result}")
    
    # 判定
    if improved_result and not any(kw in improved_result for kw in ['｜', 'ポケモン', 'マンホール', 'ポケふた', '周辺', '位置', '隣接']):
        print("✓ 改善: クリーンなアドレスを抽出")
    elif not improved_result and (any(kw in old_result for kw in ['｜', 'ポケモン', 'マンホール', 'ポケふた']) if old_result else False):
        print("✓ 改善: ノイズを含む結果をフィルタリング")
    else:
        print("△ 検証が必要")

print("\n" + "=" * 60)
