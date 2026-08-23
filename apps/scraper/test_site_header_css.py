"""site-header.css がトークンから外れていないかを検査する。

色・寸法の正は写真館（nishiokya/pokefuta）の `src/app/site-chrome-tokens.css`。
図鑑側はその値を `:root` にコピーして使う。

以前は「写真館の実測px を site-header.css に書き写す」運用で、写真館側を
変更するたびに図鑑側が黙って取り残されていた。リポジトリが別なのでビルド時に
値を突き合わせることはできないが、**コピーした値を使わず生の hex / px を
書き足す**という実際の壊れ方はここで検知できる。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

CSS_PATH = Path(__file__).resolve().parents[1] / "web" / "assets" / "site-header.css"

ROOT_BLOCK_RE = re.compile(r":root\s*\{(.*?)\}", re.DOTALL)
DECLARATION_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
PX_RE = re.compile(r"\b\d+(?:\.\d+)?px\b")

# 寸法トークンのうち、値の偶然一致が起きにくく直書きを禁じたいもの
SIZE_TOKENS = {"--chrome-height", "--chrome-tap-min", "--chrome-bottomnav-height"}


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _tokens(css: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for block in ROOT_BLOCK_RE.findall(css):
        for name, value in DECLARATION_RE.findall(block):
            tokens[name] = value.strip()
    return tokens


def _css_without_root_blocks(css: str) -> str:
    return ROOT_BLOCK_RE.sub("", css)


class SiteHeaderTokenTest(unittest.TestCase):
    def setUp(self) -> None:
        self.css = _css()
        self.tokens = _tokens(self.css)
        self.rules = _css_without_root_blocks(self.css)

    def test_token_block_exists(self):
        self.assertIn("--chrome-height", self.tokens)
        self.assertIn("--chrome-tap-min", self.tokens)
        self.assertIn("--chrome-accent", self.tokens)

    def test_no_raw_token_values_outside_root(self):
        """トークンと同じ値を var() を使わず直書きしていないこと。

        検査対象は「色」と「バーの寸法」だけに絞る。角丸や余白の px は
        用途が違っても値が偶然一致する（例: padding 9px と角丸 9px）ので、
        全 px を対象にすると誤検知でテストが信用されなくなる。
        実際の壊れ方は #7b63a8 のような色の直書きなので、そこを固く見る。
        """
        checked = {
            name: value
            for name, value in self.tokens.items()
            if HEX_RE.fullmatch(value) or name in SIZE_TOKENS
        }
        offenders = [
            f"{value} は var({name}) を使うこと"
            for name, value in checked.items()
            if value != "0px" and re.search(rf"(?<![\w-]){re.escape(value)}(?![\w-])", self.rules)
        ]
        self.assertEqual(offenders, [], "トークン値の直書きがある: " + "; ".join(offenders))

    def test_every_referenced_token_is_defined(self):
        referenced = set(re.findall(r"var\((--chrome-[\w-]+)", self.css))
        missing = sorted(referenced - set(self.tokens))
        self.assertEqual(missing, [], f"未定義のトークンを参照している: {missing}")

    def test_tap_targets_meet_the_minimum(self):
        """SP のタップ領域は 44px 以上。以前は 32px / 文字11px まで潰していた。"""
        self.assertEqual(self.tokens["--chrome-tap-min"], "44px")
        for selector in (".site-switch__trigger", ".site-auth__login", ".site-auth__signup", ".site-tab", ".site-footer__link"):
            block = re.search(rf"{re.escape(selector)}\s*(?:,[^{{]*)?\{{(.*?)\}}", self.css, re.DOTALL)
            self.assertIsNotNone(block, f"{selector} が見つからない")
            self.assertIn("var(--chrome-tap-min)", block.group(1), f"{selector} に最小タップ領域が無い")

    def test_single_pc_breakpoint(self):
        """ブレークポイントは 1024px の1本だけ。720px の段は写真館と食い違うので廃止した。

        360px の段も廃止した。「極小幅では文字を詰める」ルールを段で持っていたため、
        361〜396px の帯だけ詰まらず、英語のヘッダー（Pokéfuta｜Directory +
        Login/Sign up で 397px 必要）が iPhone のほぼ全機種ではみ出していた。
        いまは clamp() で連続的に詰めるので段はいらない。段を足して直そうとしないこと。
        """
        # コメント内にも他ファイルの @media を引用しているので、先に落とす
        css = re.sub(r"/\*.*?\*/", "", self.css, flags=re.DOTALL)
        widths = set(re.findall(r"@media\s*\(\s*(?:min|max)-width:\s*([\d.]+px)\s*\)", css))
        # 759.98px はクロムのレイアウト用ではなく、pokefuta-map.css が
        # @media (min-width: 760px) でボトムシートをフローティングパネルへ
        # 切り替える境界に合わせたもの。ここを跨いで打ち消すとPCの地図が壊れる
        self.assertEqual(
            widths, {"1024px", "759.98px"}, f"想定外のブレークポイント: {sorted(widths)}"
        )

    def test_header_can_shrink(self):
        """ヘッダーの中身が縮まないと、長いロケールで横にはみ出す。

        はみ出すとモバイルブラウザはページ全体を縮小表示し、sticky ヘッダーと
        fixed 下タブが視覚ビューポートからズレて本文に重なる。実測での回帰検知は
        test_mobile_viewport.py（ヘッドレス）が担当し、ここは書き戻しを止めるための
        静的な歯止め。
        """
        switch = re.search(r"\n\.site-switch\s*\{(.*?)\}", self.css, re.DOTALL)
        self.assertIsNotNone(switch, ".site-switch が見つからない")
        self.assertNotIn("flex: 0 0 auto", switch.group(1),
                         ".site-switch を縮まなくするとヘッダーがはみ出す")
        self.assertIn("min-width: 0", switch.group(1))

        brand = re.search(r"\.site-header__brand-name\s*\{(.*?)\}", self.css, re.DOTALL)
        self.assertIsNotNone(brand, ".site-header__brand-name が見つからない")
        self.assertIn("text-overflow: ellipsis", brand.group(1),
                      "ブランド名は最後の逃げ道として省略できること")

    def test_anchor_targets_clear_the_sticky_header(self):
        """ページ内リンクの着地点がヘッダーの下に潜らないこと。"""
        rule = re.search(r"body\.has-site-header \[id\]\s*\{(.*?)\}", self.css, re.DOTALL)
        self.assertIsNotNone(rule, "アンカー着地点の scroll-margin-top が無い")
        self.assertIn("var(--chrome-sticky-offset)", rule.group(1))

    def test_mark_is_not_hidden_on_mobile(self):
        """SP でモンスターボールを消すとサイト帯のブランドが SP だけ無くなる。"""
        for block in re.findall(r"\.site-header__mark\s*\{(.*?)\}", self.css, re.DOTALL):
            self.assertNotIn("display: none", block)

    def test_chrome_outranks_map_overlays(self):
        """全画面地図のオーバーレイ（.map-hero-card 800 / #controls 1000）より
        共通クロムを前面に出すこと。共通の z-index 50 のままだとサイトスイッチャーの
        メニューがヒーローカードの下に潜って押せなくなる。"""
        for selector in (".site-header", ".site-tabs"):
            rule = re.search(
                rf"body\.has-site-header\.pokefuta-map-page {re.escape(selector)}\s*\{{(.*?)\}}",
                self.css, re.DOTALL)
            self.assertIsNotNone(rule, f"{selector} の地図ページ用 z-index が無い")
            z = re.search(r"z-index:\s*(\d+)", rule.group(1))
            self.assertIsNotNone(z)
            self.assertGreater(int(z.group(1)), 1000, f"{selector} が地図オーバーレイに負ける")

    def test_full_screen_map_reserves_room_for_both_bars(self):
        block = re.search(r"\.map-stage[^{]*\{(.*?)\}", self.css, re.DOTALL)
        self.assertIsNotNone(block)
        self.assertIn("var(--chrome-height)", block.group(1))
        self.assertIn("var(--chrome-bottomnav-height)", block.group(1))


if __name__ == "__main__":
    unittest.main()
