"""都道府県ごとの「現地写真コンプリート」状況を数える。

/prefectures/ の一覧カードと /summary/ の「まだ写真が投稿されていない
ポケふた」が同じ数字を出すための唯一の集計元。それぞれが自前で数えていた
ときは `installed: false`（設置予定）の扱いが揃っておらず、同じデータから
違う残り枚数が出る状態だった。

「県単位」で数えるのがこのモジュールの主目的。残り枚数（全国で十数枚）は
埋まるのが遅く、トップに出しても数字が何ヶ月も動かない。一方で残っている
のは少数の県に固まっているので、県を単位にすると「残りN県」という動く
数字になる。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrefectureCompletion:
    """1都道府県ぶんの写真掲載状況。"""

    prefecture: str
    total: int
    with_photo: int

    @property
    def missing(self) -> int:
        return max(self.total - self.with_photo, 0)

    @property
    def is_complete(self) -> bool:
        # ポケふたが1枚も無い県は「コンプリート」ではなく集計対象外。
        # build_completion() 側で除外済みだが、単体で使われたときのために
        # ここでも total==0 を弾く。
        return self.total > 0 and self.missing == 0

    @property
    def coverage(self) -> int:
        return round(self.with_photo / self.total * 100) if self.total else 0


@dataclass(frozen=True)
class CompletionRollup:
    """全国ぶんのまとめ。`prefectures` はポケふたが1枚以上ある県のみ。"""

    prefectures: tuple[PrefectureCompletion, ...]

    @property
    def listed_count(self) -> int:
        """ポケふたが存在する都道府県の数。47ではない点に注意。"""
        return len(self.prefectures)

    @property
    def complete(self) -> tuple[PrefectureCompletion, ...]:
        return tuple(p for p in self.prefectures if p.is_complete)

    @property
    def incomplete(self) -> tuple[PrefectureCompletion, ...]:
        """残り枚数の少ない順。次に達成できる県を先頭に置くため。"""
        return tuple(
            sorted(
                (p for p in self.prefectures if not p.is_complete),
                key=lambda p: (p.missing, p.prefecture),
            )
        )

    @property
    def complete_count(self) -> int:
        return len(self.complete)

    @property
    def incomplete_count(self) -> int:
        return len(self.incomplete)

    @property
    def missing_total(self) -> int:
        return sum(p.missing for p in self.prefectures)

    def by_prefecture(self, prefecture: str) -> PrefectureCompletion | None:
        for entry in self.prefectures:
            if entry.prefecture == prefecture:
                return entry
        return None


def is_countable(record: dict) -> bool:
    """コンプリート判定に数える1枚かどうか。

    `installed is not False` は「設置予定・未設置は数えない」という
    generate_prefecture_pages.py 内で繰り返し使われている規約。まだ現地に
    無いものを「写真が足りない」と数えると、撮りに行きようのない残数が
    永遠に残る。
    """
    return record.get("installed") is not False


def build_completion(
    records_by_pref: dict[str, list[dict]],
    photo_ids: set[str],
    order: list[str] | tuple[str, ...] | None = None,
) -> CompletionRollup:
    """都道府県名 -> レコード列 と「写真があるポケふたのID集合」から集計する。

    `photo_ids` は str のIDで渡す。呼び出し側の写真データの形
    （latest-manhole-photos.json の photos dict / 別のスナップショット）に
    このモジュールを依存させないため。
    """
    names = list(order) if order else list(records_by_pref)
    entries: list[PrefectureCompletion] = []
    for name in names:
        countable = [r for r in records_by_pref.get(name, []) if is_countable(r)]
        if not countable:
            # ポケふたが無い県（未設置県）はコンプリート率の母数に入れない。
            continue
        with_photo = sum(
            1 for r in countable if str(r.get("id", "")) in photo_ids
        )
        entries.append(
            PrefectureCompletion(
                prefecture=name, total=len(countable), with_photo=with_photo
            )
        )
    return CompletionRollup(prefectures=tuple(entries))
