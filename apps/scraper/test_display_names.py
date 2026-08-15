"""display_names.attach_place_labels のテスト。

update-pokefuta.yml から update_pokefuta.py 経由で呼ばれるため、
同ワークフローのテストステップに追加すること。
"""
import json
import unittest
from pathlib import Path

from display_names import (
    attach_place_labels,
    build_place_label,
    compose_display_name,
    landmark_label,
    municipality_label,
    town_label,
)

ROOT = Path(__file__).resolve().parent.parent.parent


def rec(**kwargs):
    base = {"id": "1", "status": "active", "title": "鹿児島県/指宿市",
            "prefecture": "鹿児島県", "city": "指宿", "address": "", "pokemons": []}
    base.update(kwargs)
    return base


class MunicipalityLabelTest(unittest.TestCase):
    def test_restores_suffix_from_address(self):
        r = rec(city="指宿", address="鹿児島県指宿市湊1丁目1-1")
        self.assertEqual(municipality_label(r), "指宿市")

    def test_does_not_match_prefecture_suffix(self):
        # 「京都府京都市…」で先頭の京都府を拾わないこと
        r = rec(city="京都", address="京都府京都市右京区嵯峨中ノ島町")
        self.assertEqual(municipality_label(r), "京都市")

    def test_village_suffix(self):
        r = rec(city="小笠原", address="東京都小笠原村父島字東町")
        self.assertEqual(municipality_label(r), "小笠原村")

    def test_falls_back_to_bare_city_when_address_missing(self):
        r = rec(city="指宿", address="")
        self.assertEqual(municipality_label(r), "指宿")


class TownLabelTest(unittest.TestCase):
    def test_keeps_chome_and_banchi(self):
        # ここを切ると斑鳩町の3枚（興留7丁目3 / 5丁目5 / 2丁目1）が区別できなくなる
        r = rec(city="斑鳩", address="奈良県斑鳩町興留7丁目3")
        self.assertEqual(town_label(r, "斑鳩町"), "興留7丁目3")

    def test_handles_broken_prefecture_prefix(self):
        # 実データに「県大津市由美浜」のように県名が欠けたものがある
        r = rec(city="大津", address="県大津市由美浜")
        self.assertEqual(town_label(r, "大津市"), "由美浜")

    def test_handles_duplicated_city_in_address(self):
        r = rec(city="小千谷", address="新潟県小千谷市小千谷市城内1-8-22")
        self.assertEqual(town_label(r, "小千谷市"), "城内1-8-22")

    def test_keeps_ward_for_designated_city(self):
        r = rec(city="京都", address="京都府京都市右京区嵯峨中ノ島町")
        self.assertEqual(town_label(r, "京都市"), "右京区嵯峨中ノ島町")

    def test_normalizes_ideographic_space_in_address(self):
        r = rec(city="北九州", address="福岡県北九州市小倉北区浅野三丁目5　あさの汐風公園")
        self.assertEqual(town_label(r, "北九州市"), "小倉北区浅野三丁目5 あさの汐風公園")


class LandmarkLabelTest(unittest.TestCase):
    def test_normalizes_ideographic_space(self):
        r = rec(building="指宿警察署　指宿中央交番")
        self.assertEqual(landmark_label(r, "指宿市"), "指宿警察署 指宿中央交番")

    def test_drops_leading_city_name(self):
        r = rec(building="指宿市 指宿図書館")
        self.assertEqual(landmark_label(r, "指宿市"), "指宿図書館")


class BuildPlaceLabelTest(unittest.TestCase):
    def test_prefers_landmark(self):
        r = rec(address="鹿児島県指宿市湯の浜5丁目25-18", building="砂むし会館砂楽")
        self.assertEqual(build_place_label(r), "指宿市 砂むし会館砂楽")

    def test_falls_back_to_address(self):
        r = rec(city="斑鳩", address="奈良県斑鳩町興留7丁目3")
        self.assertEqual(build_place_label(r), "斑鳩町 興留7丁目3")

    def test_prefer_address_ignores_landmark(self):
        r = rec(city="東大阪", address="大阪府東大阪市松原南1-1", building="花園中央公園")
        self.assertEqual(build_place_label(r), "東大阪市 花園中央公園")
        self.assertEqual(build_place_label(r, prefer_address=True), "東大阪市 松原南1-1")

    def test_never_contains_pokemon_name(self):
        r = rec(address="鹿児島県指宿市湯の浜5丁目25-18", building="砂むし会館砂楽",
                pokemons=["ブースター"])
        self.assertNotIn("ブースター", build_place_label(r))


class AddressCandidatesTest(unittest.TestCase):
    def test_stages_are_readable(self):
        from display_names import address_candidates
        self.assertEqual(
            address_candidates("小倉北区室町一丁目1 リバーウォーク北九州"),
            ["小倉北区", "小倉北区室町", "小倉北区室町一丁目",
             "小倉北区室町一丁目1", "小倉北区室町一丁目1 リバーウォーク北九州"])

    def test_does_not_cut_inside_ward_or_chome(self):
        from display_names import address_candidates
        stages = address_candidates("門司区旧門司二丁目5 ノーフォーク広場")
        self.assertNotIn("門司", stages)          # 区名の途中で切らない
        self.assertNotIn("門司区旧門司二", stages)  # 丁目の途中で切らない

    def test_kanji_numeral_in_place_name_is_kept(self):
        from display_names import address_candidates
        # 「十二町」は丁目ではないので地名として残す
        self.assertEqual(address_candidates("十二町2290"), ["十二町", "十二町2290"])


class AttachPlaceLabelsTest(unittest.TestCase):
    def test_shortens_to_shortest_unique_stage(self):
        # 北九州の5枚は区＋町名まで切っても区別できる
        rows = [
            rec(id="198", city="北九州", title="福岡県/北九州市",
                address="福岡県北九州市小倉北区室町一丁目1 リバーウォーク北九州"),
            rec(id="201", city="北九州", title="福岡県/北九州市",
                address="福岡県北九州市門司区港町5 門司港レトロ地区"),
            rec(id="202", city="北九州", title="福岡県/北九州市",
                address="福岡県北九州市門司区旧門司二丁目5 ノーフォーク広場"),
        ]
        attach_place_labels(rows)
        self.assertEqual([r["place_label"] for r in rows],
                         ["北九州市 小倉北区室町", "北九州市 門司区港町", "北九州市 門司区旧門司"])

    def test_does_not_pick_stage_where_one_is_prefix_of_another(self):
        # 「松原南」と「松原南2」だと切れているのか2丁目なのか読めない
        rows = [
            rec(id="1", city="東大阪", title="大阪府/東大阪市", address="大阪府東大阪市松原南1-1"),
            rec(id="2", city="東大阪", title="大阪府/東大阪市", address="大阪府東大阪市松原南2-6"),
        ]
        attach_place_labels(rows)
        self.assertEqual([r["place_label"] for r in rows],
                         ["東大阪市 松原南1", "東大阪市 松原南2"])

    def test_landmark_is_not_replaced_by_address(self):
        # 住所側が深い段階を必要としても、衝突していない施設名は捨てない
        rows = [
            rec(id="222", city="香取", title="千葉県/香取市", address="千葉県香取市佐原イ109-14"),
            rec(id="223", city="香取", title="千葉県/香取市", address="千葉県香取市佐原イ1722-1"),
            rec(id="225", city="香取", title="千葉県/香取市",
                address="千葉県香取市佐原イ4053", building="道の駅水の郷さわら"),
        ]
        attach_place_labels(rows)
        self.assertEqual(rows[2]["place_label"], "香取市 道の駅水の郷さわら")
        self.assertEqual(rows[0]["place_label"], "香取市 佐原イ109")

    def test_colliding_landmark_falls_back_to_address(self):
        rows = [
            rec(id="209", city="東大阪", title="大阪府/東大阪市",
                address="大阪府東大阪市松原南1-1", building="花園中央公園"),
            rec(id="210", city="東大阪", title="大阪府/東大阪市",
                address="大阪府東大阪市松原南2-6", building="花園中央公園"),
            rec(id="208", city="東大阪", title="大阪府/東大阪市",
                address="大阪府東大阪市東石切町2", building="東石切公園"),
        ]
        attach_place_labels(rows)
        self.assertEqual([r["place_label"] for r in rows],
                         ["東大阪市 松原南1", "東大阪市 松原南2", "東大阪市 東石切公園"])

    def test_ambiguous_drops_shared_address(self):
        # 全員に共通の住所は何も伝えないので落とし、ポケモン名で区別する
        rows = [
            rec(id="98", city="町田", title="東京都/町田市",
                address="東京都町田市原町田5-16", pokemons=["フシギダネ"]),
            rec(id="99", city="町田", title="東京都/町田市",
                address="東京都町田市原町田5-16", pokemons=["ヒトカゲ"]),
        ]
        attach_place_labels(rows)
        self.assertEqual([r["place_label"] for r in rows], ["町田市", "町田市"])
        self.assertEqual(compose_display_name(rows[0]), "町田市（フシギダネ）")


    def test_unique_title_gets_no_label(self):
        rows = [rec(id="1", title="北海道/斜里町", city="斜里", address="北海道斜里町")]
        self.assertEqual(attach_place_labels(rows), 0)
        self.assertNotIn("place_label", rows[0])

    def test_duplicated_title_gets_label(self):
        rows = [
            rec(id="148", city="斑鳩", title="奈良県/斑鳩町", address="奈良県斑鳩町興留7丁目3"),
            rec(id="149", city="斑鳩", title="奈良県/斑鳩町", address="奈良県斑鳩町興留5丁目5"),
        ]
        self.assertEqual(attach_place_labels(rows), 2)
        self.assertEqual(rows[0]["place_label"], "斑鳩町 興留7")
        self.assertEqual(rows[1]["place_label"], "斑鳩町 興留5")
        self.assertNotIn("place_ambiguous", rows[0])

    def test_same_landmark_retries_with_address(self):
        # 東大阪の2枚はどちらも building が「花園中央公園」だが住所で分かれる
        rows = [
            rec(id="209", city="東大阪", title="大阪府/東大阪市",
                address="大阪府東大阪市松原南1-1", building="花園中央公園"),
            rec(id="210", city="東大阪", title="大阪府/東大阪市",
                address="大阪府東大阪市松原南2-6", building="花園中央公園"),
        ]
        attach_place_labels(rows)
        self.assertEqual(rows[0]["place_label"], "東大阪市 松原南1")
        self.assertEqual(rows[1]["place_label"], "東大阪市 松原南2")
        self.assertNotIn("place_ambiguous", rows[0])

    def test_retry_does_not_degrade_when_address_missing(self):
        # 住所が無いのに prefer_address で再算出すると「指宿市」だけに退化してしまう
        rows = [
            rec(id="1", address="", building="砂むし会館砂楽"),
            rec(id="2", address="", building="砂むし会館砂楽"),
        ]
        attach_place_labels(rows)
        self.assertEqual(rows[0]["place_label"], "指宿 砂むし会館砂楽")
        self.assertTrue(rows[0]["place_ambiguous"])

    def test_same_address_marks_ambiguous(self):
        # 町田市は6枚とも原町田5-16。場所では原理的に区別できない
        rows = [
            rec(id="98", city="町田", title="東京都/町田市",
                address="東京都町田市原町田5-16", pokemons=["フシギダネ"]),
            rec(id="99", city="町田", title="東京都/町田市",
                address="東京都町田市原町田5-16", pokemons=["ヒトカゲ"]),
        ]
        attach_place_labels(rows)
        self.assertEqual(rows[0]["place_label"], "町田市")
        self.assertTrue(rows[0]["place_ambiguous"])
        self.assertTrue(rows[1]["place_ambiguous"])

    def test_deleted_records_are_ignored(self):
        rows = [
            rec(id="1", status="deleted", title="東京都/町田市", place_label="古い名前"),
            rec(id="2", city="町田", title="東京都/町田市", address="東京都町田市原町田5-16"),
        ]
        self.assertEqual(attach_place_labels(rows), 0)
        self.assertNotIn("place_label", rows[0])
        self.assertNotIn("place_label", rows[1])

    def test_stale_fields_are_removed(self):
        rows = [rec(id="1", title="北海道/斜里町",
                    place_label="古い名前", place_ambiguous=True)]
        attach_place_labels(rows)
        self.assertNotIn("place_label", rows[0])
        self.assertNotIn("place_ambiguous", rows[0])


class ComposeDisplayNameTest(unittest.TestCase):
    def test_plain_label(self):
        r = rec(place_label="指宿市 砂むし会館砂楽", pokemons=["ブースター"])
        self.assertEqual(compose_display_name(r), "指宿市 砂むし会館砂楽")

    def test_ambiguous_gets_pokemon(self):
        r = rec(place_label="町田市 原町田5-16", place_ambiguous=True,
                pokemons=["フシギダネ"])
        self.assertEqual(compose_display_name(r), "町田市 原町田5-16（フシギダネ）")

    def test_always_with_pokemon_for_kml(self):
        r = rec(place_label="指宿市 砂むし会館砂楽", pokemons=["ブースター"])
        self.assertEqual(compose_display_name(r, always_with_pokemon=True),
                         "指宿市 砂むし会館砂楽（ブースター）")

    def test_falls_back_to_title(self):
        r = rec(title="北海道/斜里町")
        self.assertEqual(compose_display_name(r), "北海道/斜里町")


class DatasetInvariantTest(unittest.TestCase):
    """公開データの実測値を固定する。"""

    def setUp(self):
        path = ROOT / "docs" / "pokefuta.ndjson"
        self.rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def test_place_labelはポケモン名を含まない(self):
        pokemons = {p for r in self.rows for p in r.get("pokemons", [])}
        for r in self.rows:
            label = r.get("place_label")
            if not label:
                continue
            hit = [p for p in pokemons if p in label]
            self.assertEqual(hit, [], f"id={r['id']} の place_label にポケモン名: {label}")

    def test_曖昧なのは同じplace_labelを共有するものだけ(self):
        # 件数はハードコードしない。住所の精度が上がると減る
        # （例: PR #410 の住所修正で台東区上野の2件が解消し16->14になる）
        from collections import Counter
        counts = Counter(r["place_label"] for r in self.rows if r.get("place_label"))
        amb = [r for r in self.rows if r.get("place_ambiguous")]
        self.assertTrue(amb, "place_ambiguous が1件も無いのは想定外")
        for r in amb:
            self.assertGreater(counts[r["place_label"]], 1,
                               f"id={r['id']} は一意なのに place_ambiguous が立っている")
        # 逆向き: 共有しているのに立っていないものが無いこと
        for r in self.rows:
            label = r.get("place_label")
            if label and counts[label] > 1:
                self.assertTrue(r.get("place_ambiguous"),
                                f"id={r['id']} は place_label を共有するのに印が無い")

    def test_表示名は全件一意になる(self):
        from display_names import compose_display_name as compose
        names = {}
        for r in self.rows:
            names.setdefault(compose(r), []).append(r["id"])
        duplicated = {k: v for k, v in names.items() if len(v) > 1}
        self.assertEqual(duplicated, {}, f"表示名が重複している: {duplicated}")


if __name__ == "__main__":
    unittest.main()
