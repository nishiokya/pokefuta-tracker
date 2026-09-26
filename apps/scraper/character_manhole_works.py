"""作品LPの掲載方針。全国一覧・作品ページ・sitemapで同じ定義を使う。"""

from __future__ import annotations

from dataclasses import dataclass

# ガンダムマンホールは character_manholes.ndjson とは別の独立データセット（docs/gmanhole.ndjson）で、
# "work" を持たない。全国一覧・作品ガイド・sitemap で同じ作品として扱うための定義。
GUNDAM_WORK = "機動戦士ガンダム"
GUNDAM_WORK_NAME = "機動戦士ガンダム（ガンダムマンホール）"
GUNDAM_WORK_QUERY = "gundam"  # gmanhole_map.html の ?work= に渡す値（chk-gundam を選択する特別値）
GUNDAM_MARKER_COLOR = "#0044aa"
GUNDAM_MARKER_LABEL = "G"

# 全国一覧と作品ガイドが共有する character-work.css のキャッシュバスター。
# 片方だけ上げると、もう片方のページで古いCSSがキャッシュに残るので、ここ1か所で管理する。
CHARACTER_CSS_VERSION = "20260926b"


@dataclass(frozen=True)
class WorkPage:
    slug: str
    name: str
    search_name: str
    works: tuple[str, ...]
    intro: str
    guide: str
    question: str
    answer: str

    @property
    def path(self) -> str:
        return f"characters/{self.slug}/"

    @property
    def map_query(self) -> str:
        return {"idolmaster": "idolmaster", "gundam": GUNDAM_WORK_QUERY}.get(self.slug, self.works[0])


WORK_PAGES = (
    WorkPage(
        "gundam", "機動戦士ガンダム", "ガンダム", (GUNDAM_WORK,),
        "機動戦士ガンダムのマンホール（ガンダムマンホール）を、都道府県・市町村・設置場所から探せます。"
        "道の駅や駅前、観光施設など、全国の設置場所と住所・出典をまとめました。",
        "北海道から九州まで広く分布しています。都道府県ごとの一覧で行き先を決めてから、"
        "地図で近くの設置場所をまとめて確認すると、回る順番を考えやすくなります。",
        "ガンダムマンホールはどこにありますか？",
        "このページでは、掲載データにある全国の設置場所を都道府県・市町村別に紹介しています。"
        "最新の設置状況や撤去・移設の情報は、各設置場所の出典（ガンダムマンホール公式サイト）をご確認ください。",
    ),
    WorkPage(
        "idolmaster", "アイドルマスター", "アイマス（ふたマス）",
        ("アイドルマスター", "アイドルマスター シンデレラガールズ",
         "アイドルマスター ミリオンライブ！", "アイドルマスター SideM",
         "アイドルマスター シャイニーカラーズ", "学園アイドルマスター"),
        "アイドルマスターのマンホール「ふたマス!!!!!!」を、アイドル名・シリーズ・設置場所から探せます。"
        "高槻やよい、前川みく、渡辺みのり、姫崎莉波など、各地のアイドルに会いに行くための一覧です。",
        "担当アイドルから設置場所を選ぶほか、シリーズ別の地図も利用できます。"
        "複数の地域にまたがるため、まず行き先の市町村を確認してから旅程を組んでください。",
        "ふたマスとは何ですか？",
        "『アイドルマスター』シリーズ20周年を記念し、地方自治体と連携してアイドルの絵柄のマンホールを設置するプロジェクトです。"
        "このページでは掲載データに収録した設置場所を紹介しています。最新の展開は各出典や公式サイトをご確認ください。",
    ),
    WorkPage(
        "zombieland-saga", "ゾンビランドサガ", "ゾンビランドサガ", ("ゾンビランドサガ",),
        "ゾンビランドサガのマンホールを、キャラクターや佐賀県内の市町村から探せます。設置場所と住所、出典をまとめました。",
        "佐賀県内のどの市町村を訪ねるか決め、近い設置場所を地図で確認すると回る順番を考えやすくなります。",
        "佐賀県内の設置場所を市町村別に探せますか？",
        "はい。市町村ごとの一覧と地図から探せます。設置場所の名称や住所も併記しています。",
    ),
    WorkPage(
        "romancing-saga", "ロマンシング サガ", "ロマサガ（ロマンシング サガ）", ("ロマンシング サガ",),
        "ロマンシング サガのマンホールを、佐賀県内の設置場所から探せます。キャラクター・市町村・住所を一覧で確認できます。",
        "ロマサガの設置場所は市町村ごとにまとめています。旅の行き先を選んでから、同じ地域の蓋を地図で探してみてください。",
        "ロマサガのマンホールはどこで探せますか？",
        "掲載データにある佐賀県内のマンホールを、このページの市町村別一覧で紹介しています。地図はロマンシング サガで絞り込んで開けます。",
    ),
    WorkPage(
        "yowamushi-pedal", "弱虫ペダル", "弱虫ペダル", ("弱虫ペダル",),
        "弱虫ペダルのマンホールを、長崎県内の市町村・キャラクター・設置場所から探せます。訪問先の住所と出典を確認できます。",
        "市町村ごとに設置場所を確認し、徒歩や自転車など移動手段に合わせて回る範囲を決めてください。地図の位置だけで走行可能な経路とは判断しないでください。",
        "弱虫ペダルのマンホールカードも探せますか？",
        "このページはマンホール本体の設置場所一覧です。カードの配布場所や在庫とは異なるため、配布については自治体などの案内を確認してください。",
    ),
    WorkPage(
        "tokai-onair", "東海オンエア", "東海オンエア", ("東海オンエア",),
        "東海オンエアのマンホールを、愛知県岡崎市の設置場所から探せます。場所の名称・住所・出典をまとめた一覧です。",
        "岡崎市内の訪問先を地図で確認し、近くの蓋をまとめて回る計画に役立ててください。撮影時は通行や施設の利用を妨げないようにしましょう。",
        "東海オンエアのマンホールの場所を地図で見られますか？",
        "はい。東海オンエアで絞り込んだ地図と、各設置場所の地図リンクを用意しています。",
    ),
    WorkPage(
        "chibi-maruko", "ちびまる子ちゃん", "ちびまる子ちゃん", ("ちびまる子ちゃん",),
        "ちびまる子ちゃんのマンホールを、静岡市内の設置場所から探せます。まる子・友蔵・たまちゃんなどの絵柄と住所を確認できます。",
        "静岡市内でもエリアが分かれているため、一覧の区名と設置場所を確認してから回る順番を決めると便利です。",
        "ちびまる子ちゃんのマンホールはどこにありますか？",
        "このページでは静岡市内の掲載データを、区・設置場所ごとに紹介しています。最新の設置案内は各場所の出典をご確認ください。",
    ),
)


def page_for_work(work: str) -> WorkPage | None:
    return next((page for page in WORK_PAGES if work in page.works), None)


def available_pages(records: list[dict]) -> list[WorkPage]:
    """呼び出し側で撤去・未設置を除いたデータを渡す。空のLPは生成しない。"""
    works = {record.get("work") for record in records}
    return [page for page in WORK_PAGES if works.intersection(page.works)]


def gundam_work_records(records: list[dict]) -> list[dict]:
    """gmanhole.ndjson のレコードを、作品ガイドが読める形（work / 出典 / 色）に揃えたコピーを返す。

    ガンダムのデータにはキャラクター名が無く、title が設置場所の名前なので、
    landmark にも同じ値を入れる。画像URLは他サイトの相対パスなので持ち込まない。
    """
    return [
        {
            **record,
            "work": GUNDAM_WORK,
            "character": "",
            "landmark": record.get("title") or "",
            "official_url": record.get("detail_url") or "",
            "marker_color": GUNDAM_MARKER_COLOR,
            "marker_label": GUNDAM_MARKER_LABEL,
        }
        for record in records
    ]
