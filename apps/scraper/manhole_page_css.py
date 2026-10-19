"""詳細ページ（/manholes/<id>/）の CSS。

generate_manhole_pages.py（日本語）と generate_manhole_pages_i18n.py（訳）が同じものを使う。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from photo_caption import CAPTION_ELLIPSIS_CSS  # noqa: E402

PAGE_CSS = f"""    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.6;
      color: #333;
      background: #fff8ec;
      /* ⚠️ padding-top を入れないこと。inject_site_header.py が入れる全幅ヘッダーが
         そのぶん下へ押し出され、ヘッダーの上にページ背景の帯が出る。
         本文の上余白は .container の margin-top で取る */
      padding: 0 16px 16px;
    }}

    .container {{
      max-width: var(--page-max-wide, 1120px);
      margin: 16px auto 0;
      background: white;
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    }}

    h1 {{
      font-size: 24px;
      margin-bottom: 16px;
      color: #1a1a1a;
    }}

    h2 {{
      font-size: 20px;
      margin: 24px 0 12px;
      padding-bottom: 8px;
      border-bottom: 2px solid #e0e0e0;
    }}

    h3 {{
      font-size: 18px;
      margin-bottom: 8px;
    }}

    .cta-primary {{
      display: block;
      background: #dc3545;
      color: white;
      text-align: center;
      padding: 16px 24px;
      border-radius: 8px;
      text-decoration: none;
      font-size: 18px;
      font-weight: bold;
      margin: 24px 0;
      transition: background 0.2s;
    }}

    .cta-primary:hover {{
      background: #c82333;
    }}

    .cta-secondary {{
      display: inline-block;
      background: #007bff;
      color: white;
      padding: 12px 20px;
      border-radius: 6px;
      text-decoration: none;
      margin: 8px 8px 8px 0;
      transition: background 0.2s;
    }}

    .cta-secondary:hover {{
      background: #0056b3;
    }}

    .photo-section img {{
      max-width: 100%;
      height: auto;
      border-radius: 8px;
      margin-top: 12px;
    }}

    .pokemon-list {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 16px;
      margin-top: 12px;
    }}

    .pokemon-card {{
      background: #f8f9fa;
      padding: 16px;
      border-radius: 8px;
      border: 1px solid #e0e0e0;
    }}
    .pokemon-card h3 a {{
      color: inherit;
      text-decoration: none;
    }}
    .pokemon-card h3 a:hover, .pokemon-card h3 a:focus {{
      text-decoration: underline;
    }}

    .pokemon-card .en-name {{
      color: #666;
      font-size: 14px;
    }}

    .pokemon-card .types,
    .pokemon-card .generation {{
      font-size: 14px;
      margin-top: 4px;
    }}

    dl {{
      display: grid;
      grid-template-columns: 5em 1fr;
      gap: 3px 8px;
      margin-top: 8px;
    }}

    dt {{
      font-weight: bold;
      margin-top: 0;
    }}

    dd {{
      margin-left: 0;
      color: #555;
    }}

    .official-link {{
      margin-top: 16px;
    }}

    .official-link a {{
      color: #007bff;
      text-decoration: none;
    }}

    .official-link a:hover {{
      text-decoration: underline;
    }}

    footer {{
      margin-top: 32px;
      padding-top: 16px;
      border-top: 1px solid #e0e0e0;
      text-align: center;
      color: #666;
      font-size: 14px;
    }}

    .related-list {{
      list-style: none;
      margin-top: 0;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}

    .related-list a {{
      color: #1a6fd4;
      text-decoration: none;
      font-weight: 500;
      flex: 1;
    }}

    .related-list a:hover {{
      text-decoration: underline;
    }}

    .related-list li {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 14px;
      background: #fafaf8;
      border-radius: 8px;
      border: 1px solid #e8e3db;
      flex-wrap: wrap;
      gap: 4px;
      transition: background 0.15s;
    }}

    .related-list li:hover {{
      background: #f3ede4;
    }}

    .distance {{
      font-size: 13px;
      color: #666;
      white-space: nowrap;
    }}

    .trip-stops {{ padding-left: 0; }}
    .trip-here {{
      font-size: 12px;
      font-weight: 700;
      color: #6b4aa2;
      white-space: nowrap;
      margin-right: 6px;
    }}

    /* HERO card */
    .hero-card {{
      border-radius: 16px;
      overflow: hidden;
      border: 1px solid #e8d8c0;
      margin-bottom: 24px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.10);
    }}

    .hero-photo img {{
      width: 100%;
      aspect-ratio: 4 / 3;
      object-fit: cover;
      display: block;
    }}

    .hero-photo-placeholder {{
      width: 100%;
      aspect-ratio: 4 / 3;
      background: linear-gradient(135deg, #f5ede0 0%, #ede0cf 100%);
      border: 2px dashed #d4b896;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 10px;
      text-decoration: none;
      cursor: pointer;
      transition: background 0.15s, transform 0.15s, box-shadow 0.15s;
    }}

    .hero-photo-placeholder:hover {{
      background: linear-gradient(135deg, #eeddd0 0%, #e4d3be 100%);
      transform: translateY(-1px);
      box-shadow: 0 4px 16px rgba(180, 120, 60, 0.12);
    }}

    .placeholder-camera {{
      font-size: 40px;
      opacity: 0.6;
      display: block;
    }}

    .placeholder-title {{
      font-size: 14px;
      font-weight: 600;
      color: #8a6440;
    }}

    .placeholder-sub {{
      font-size: 13px;
      color: #b08050;
      text-decoration: underline;
      text-underline-offset: 3px;
    }}

    .hero-photo-preinstall {{
      background: linear-gradient(135deg, #f0ede6 0%, #e6e1d5 100%);
      border-color: #b8ab8e;
      cursor: default;
    }}

    .hero-photo-preinstall .placeholder-title {{
      color: #6b5d44;
    }}

    .hero-photo-preinstall .placeholder-sub {{
      color: #8a7d63;
      text-decoration: none;
    }}

    .hero-body {{
      padding: 20px 20px 24px;
    }}

    /* PC は本文が --page-max-wide まで広がるので、1カラムのままだと写真が
       画面より大きくなる。写真と見出し・タグ・投稿ボタンを横に並べる */
    @media (min-width: 1024px) {{
      .hero-card {{
        display: grid;
        grid-template-columns: minmax(0, 6fr) minmax(0, 5fr);
        align-items: center;
      }}

      .hero-body {{
        padding: 28px 32px;
      }}
    }}

    .hero-region {{
      font-size: 13px;
      color: #888;
      margin-bottom: 6px;
      letter-spacing: 0.02em;
    }}

    .hero-region > * + *::before {{
      content: "›";
      display: inline-block; /* リンクの下線を区切り記号に付けない */
      margin: 0 .35em;
    }}

    .hero-region a {{
      color: inherit;
      text-decoration: underline;
      text-decoration-color: #ccc;
      text-underline-offset: 2px;
    }}

    h1.hero-title {{
      font-size: 21px;
      font-weight: 700;
      margin-bottom: 14px;
      line-height: 1.45;
      color: #1a1a1a;
      letter-spacing: -0.01em;
    }}

    .hero-pokemon-tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 14px;
    }}

    .hero-tag {{
      background: #fff8e1;
      border: 1px solid #f9c940;
      border-radius: 20px;
      padding: 3px 11px;
      font-size: 13px;
      font-weight: 500;
      color: #7a5c00;
    }}

    a.hero-tag {{
      text-decoration: none;
      color: #7a5c00;
    }}

    a.hero-tag:hover {{
      background: #fde98a;
      border-color: #e6b800;
    }}

    .hero-stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin-bottom: 18px;
    }}

    .hero-badge {{
      background: #eef0ff;
      border: 1px solid #b8c0f0;
      border-radius: 20px;
      padding: 4px 13px;
      font-size: 12px;
      font-weight: 600;
      color: #3a4fc7;
      letter-spacing: 0.01em;
    }}

    a.hero-badge-anchor {{
      text-decoration: none;
    }}

    a.hero-badge-anchor:hover, a.hero-badge-anchor:focus {{
      text-decoration: underline;
      text-underline-offset: 3px;
    }}

    .design-note {{
      font-size: 13px;
      color: #777;
      margin-bottom: 10px;
    }}

    .design-work {{
      display: block;
      font-size: 12px;
      color: #888;
      margin-top: 2px;
    }}

    .design-tiles {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}

    @media (min-width: 900px) {{
      .design-tiles {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    }}

    .design-tile a {{
      display: flex;
      flex-direction: column;
      gap: 2px;
      height: 100%;
      padding: 8px;
      border: 1px solid #eee;
      border-radius: 12px;
      background: #fff;
      color: inherit;
      text-decoration: none;
    }}

    .design-tile-thumb {{
      display: flex;
      align-items: center;
      justify-content: center;
      aspect-ratio: 3 / 2;
      border-radius: 8px;
      overflow: hidden;
      background: #f3efe8;
      margin-bottom: 4px;
    }}

    .design-tile-thumb img {{ width: 100%; height: 100%; object-fit: cover; }}

    .design-tile-thumb--empty {{ font-size: 12px; color: #b08050; }}

    .design-tile-title {{
      font-size: 13px;
      font-weight: 600;
      color: #1a6fd4;
      line-height: 1.35;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .hero-badge-secondary {{
      background: #f0f9ff;
      border-color: #bae6fd;
      color: #0369a1;
    }}

    .hero-actions {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
    }}

    .btn-photo-upload {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      width: 100%;
      min-height: 52px;
      border-radius: 14px;
      padding: 14px 16px;
      font-size: 15px;
      font-weight: 700;
      letter-spacing: 0.01em;
      background: #fff0f3;
      color: #c0394b;
      border: 1.5px solid #f5c0ca;
      text-decoration: none;
      cursor: pointer;
      box-shadow: 0 1px 4px rgba(0,0,0,0.07);
      transition: background 0.15s, box-shadow 0.15s, transform 0.15s;
    }}

    .btn-photo-upload:hover {{
      background: #ffe4ea;
      box-shadow: 0 3px 10px rgba(192,57,75,0.14);
      transform: translateY(-1px);
    }}

    .photo-upload-note {{
      margin: -2px 0 0;
      font-size: 11.5px;
      line-height: 1.5;
      text-align: center;
      color: #8a7f72;
    }}

    .action-icon {{
      width: 36px;
      height: 36px;
      display: block;
      flex-shrink: 0;
    }}

    .section-card {{
      background: #fff;
      border: 1px solid #ede8df;
      border-radius: 10px;
      padding: 16px 18px;
      margin-bottom: 12px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }}

    .section-card h2 {{
      font-size: 15px;
      font-weight: 600;
      margin: 0 0 10px;
      padding-bottom: 8px;
      border-bottom: 1px solid #ede8df;
      color: #444;
    }}

    .link-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }}

    .link-card {{
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      min-height: 64px;
      border-radius: 12px;
      padding: 10px 6px;
      text-align: center;
      text-decoration: none;
      font-size: 12px;
      font-weight: 600;
      line-height: 1.4;
      gap: 4px;
      border: 1px solid #e6e0d6;
      box-shadow: 0 1px 4px rgba(0,0,0,0.05);
      transition: transform 0.15s, box-shadow 0.15s;
    }}

    .link-card:hover {{
      transform: translateY(-1px);
      box-shadow: 0 3px 8px rgba(0,0,0,0.10);
    }}

    .link-card span {{ display: block; }}

    .link-card--official   {{ background: #fff4f0; color: #c0392b; border-color: #f5c0b0; }}
    .link-card--internal   {{ background: #f8f4ff; color: #5a3fa0; border-color: #d8c8f5; }}
    .link-card--share-x    {{ background: #f5f5f5; color: #444; border-color: #d8d8d8; }}
    .link-card--share-line {{ background: #f0faf5; color: #217a48; border-color: #b0e0c8; }}
    .link-card--share      {{ background: #f8f4ff; color: #5a3fa0; border-color: #d8c8f5; cursor: pointer; }}

    .related-list--cards li {{
      display: flex;
      gap: 12px;
      align-items: center;
      border-radius: 12px;
      padding: 10px 12px;
      background: #fff;
      border: 1px solid #e8e3db;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      transition: background 0.15s;
    }}

    .related-list--cards li:hover {{
      background: #f8f4ee;
    }}

    .icon {{
      display: inline-block;
      width: 18px;
      height: 18px;
      vertical-align: middle;
      flex-shrink: 0;
    }}

    .icon-sm {{ width: 14px; height: 14px; }}
    .icon-lg {{ width: 22px; height: 22px; }}
    .link-card-icon {{ width: 38px; height: 38px; display: block; }}

    .related-card-thumb {{
      width: 60px;
      height: 60px;
      flex-shrink: 0;
      border-radius: 8px;
      overflow: hidden;
      background: #f0ebe3;
    }}

    .related-card-thumb img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}

    .related-card-body {{
      flex: 1;
      display: flex;
      align-items: center;
      gap: 5px;
      min-width: 0;
    }}

    .related-card-body a {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    @media (max-width: 600px) {{
      body {{
        padding: 0 6px 6px;
        background: #fff8ec;
      }}

      .container {{
        margin-top: 6px;
        padding: 12px;
        border-radius: 10px;
      }}

      .hero-card {{
        border-radius: 12px;
      }}

      .hero-body {{
        padding: 14px 14px 18px;
      }}

      h1.hero-title {{
        font-size: 18px;
      }}

      .btn-photo-upload {{
        font-size: 16px;
        min-height: 56px;
      }}

      .section-card {{
        padding: 14px;
        border-radius: 8px;
      }}

      .pokemon-list {{
        grid-template-columns: 1fr;
      }}
    }}

    .pokemon-card .multilingual-names {{
      font-size: 13px;
      color: #666;
      margin-top: 2px;
    }}

    .hero-region-en {{
      font-size: 12px;
      color: #aaa;
      margin-bottom: 8px;
      letter-spacing: 0.03em;
    }}

    .hero-photo {{
      position: relative;
    }}

    .photo-credit {{
      position: absolute;
      bottom: 8px;
      right: 8px;
      max-width: calc(100% - 16px);
      background: rgba(0,0,0,0.55);
      color: #fff;
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 20px;
      display: flex;
      gap: 6px;
      align-items: center;
    }}

    /* 長い投稿者名は名前側を ellipsis し、日付は潰さない
       （top-page.css の .hero-footer-text / .hero-footer-cta と同じ手法） */
    .photo-credit > span:first-child {{
      {CAPTION_ELLIPSIS_CSS}
    }}

    .photo-credit > span + span {{
      flex-shrink: 0;
    }}

    a.poster-link {{
      color: #fff;
      text-decoration: underline;
      text-underline-offset: 2px;
    }}

    .photo-comment {{
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      background: rgba(0,0,0,0.50);
      color: #fff;
      font-size: 13px;
      padding: 8px 12px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .hero-badge-new {{
      background: #fff0f0;
      border-color: #ff6b6b;
      color: #c0392b;
    }}

    .hero-badge-pre {{
      background: #f1ede4;
      border-color: #b8ab8e;
      color: #6b5d44;
    }}

    .back-btn {{
      display: inline-flex;
      align-items: center;
      background: #fff;
      border: 1px solid #e0d8cc;
      border-radius: 20px;
      padding: 10px 18px;
      font-size: 14px;
      font-weight: 500;
      color: #5b4a36;
      text-decoration: none;
      margin-bottom: 12px;
      transition: background 0.15s;
    }}

    .back-btn:hover {{
      background: #f8f3eb;
    }}

    .visit-cta {{
      display: flex;
      align-items: center;
      gap: 14px;
      background: #fff;
      border: 1px solid #d8edd8;
      border-radius: 20px;
      padding: 16px 18px;
      text-decoration: none;
      box-shadow: 0 1px 4px rgba(0,0,0,0.06);
      margin-bottom: 12px;
      transition: box-shadow 0.15s, transform 0.15s;
    }}

    .visit-cta:hover {{
      transform: translateY(-1px);
      box-shadow: 0 3px 10px rgba(0,0,0,0.10);
    }}

    .visit-cta-icon {{
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: #ddf4e7;
      flex-shrink: 0;
      display: flex;
      align-items: center;
      justify-content: center;
    }}

    .visit-cta-map-icon {{
      width: 26px;
      height: 26px;
      display: block;
    }}

    .visit-cta-body {{
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}

    .visit-cta-main {{
      font-size: 15px;
      font-weight: 700;
      color: #1a1a1a;
    }}

    .visit-cta-sub {{
      font-size: 12px;
      color: #777;
    }}

    .pokemon-same-link {{
      display: block;
      font-size: 12px;
      color: #1a6fd4;
      text-decoration: none;
      margin-top: 6px;
    }}

    .pokemon-same-link:hover {{
      text-decoration: underline;
    }}

    .follow-section {{
      margin: 16px 0;
    }}

    .follow-x-card {{
      display: block;
      background: #000;
      color: #fff;
      text-decoration: none;
      border-radius: 12px;
      padding: 16px 20px;
      transition: background 0.15s, transform 0.15s;
    }}

    .follow-x-card:hover {{
      background: #1a1a1a;
      transform: translateY(-1px);
    }}

    .follow-x-title {{
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 4px;
    }}

    .follow-x-body {{
      font-size: 12px;
      color: #aaa;
      margin-bottom: 8px;
      line-height: 1.4;
    }}

    .follow-x-cta {{
      font-size: 13px;
      font-weight: 600;
      color: #1d9bf0;
    }}
    .gallery-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
      gap: 8px;
    }}
    .gallery-item {{
      margin: 0;
      position: relative;
    }}
    .gallery-item img {{
      width: 100%;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      border-radius: 10px;
      display: block;
    }}
    .gallery-credit {{
      position: absolute;
      left: 6px;
      bottom: 6px;
      font-size: 10px;
      color: #fff;
      background: rgba(0, 0, 0, .45);
      padding: 1px 6px;
      border-radius: 8px;
    }}
    .gallery-more {{
      display: inline-block;
      margin-top: 10px;
      font-size: 13px;
      font-weight: 600;
      color: #1a73e8;
      text-decoration: none;
    }}
"""
