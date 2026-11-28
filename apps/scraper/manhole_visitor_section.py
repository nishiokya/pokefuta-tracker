"""Render original visitor posts and self-labelled scenery in detail pages."""

from html import escape

from generate_gallery_pages import photo_page_url, photo_src
from photo_caption import format_display_name, format_photo_date

LABELS = {
    "ja": ("訪れた人の口コミ", "設置場所の周辺写真", "撮影", "投稿", "投稿写真を見る", "写真館の口コミを見る"),
    "en": ("Visitor notes", "Photos of the surroundings", "Taken", "Posted", "View photo", "View comments in the photo gallery"),
    "zh-TW": ("訪客留言", "設置地點周邊照片", "拍攝", "發表", "查看投稿照片", "到寫真館查看留言"),
}


def render_visitor_section(guide, studio_url, lang="ja"):
    heading, surroundings, taken, posted, see_photo, see_thread = LABELS[lang]
    sections = []
    for key, title in (("notes", heading), ("scenery", surroundings)):
        rows = []
        for entry in guide.get(key, []):
            photo_id = entry.get("photo_id")
            shot = format_photo_date(entry.get("shot_at"), lang, with_year=True)
            date = format_photo_date(entry.get("created_at"), lang, with_year=True)
            when = f"{taken} {shot}" if shot else (f"{posted} {date}" if date else "")
            name = format_display_name(entry.get("display_name"))
            by = f'<bdi translate="no">{escape(name)}</bdi>' if name else ""
            credit = " · ".join(filter(None, (by, escape(when))))
            if key == "scenery":
                if photo_id:
                    rows.append(
                        f'<figure><a href="{photo_page_url(photo_id)}"><img src="{photo_src(photo_id)}" '
                        f'alt="{title}" width="360" height="240" loading="lazy" decoding="async"></a>'
                        f'<figcaption>{credit}</figcaption></figure>'
                    )
            else:
                url, label = (photo_page_url(photo_id), see_photo) if photo_id else (studio_url, see_thread)
                rows.append(
                    f'<li><blockquote dir="auto"><span lang="ja">{escape(entry["content"])}</span></blockquote>'
                    f'<div class="note-source"><span>{credit}</span>'
                    f'<a href="{escape(url)}">{label}</a></div></li>'
                )
        if rows:
            tag = "ul" if key == "notes" else "div"
            sections.append(
                f'<section class="visitor-section section-card"><h2>{title}</h2>'
                f'<{tag} class="visitor-{key}">{"".join(rows)}</{tag}></section>'
            )
    return "".join(sections)
