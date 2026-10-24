# 特集の書き方

特集ページ `https://data.pokefuta.com/features/<slug>/` は、このフォルダの2つのファイルからできています。

| ファイル | 中身 | 書く人 |
|---|---|---|
| `<slug>.json` | タイトル・公開日・載せる蓋の ID・日程・ニュース・リンク | 書式は `apps/scraper/features.py` の先頭 |
| `<slug>.html` | 本文（読み物の部分）。無い特集もある | HTML で書く |

蓋の一覧・地図・ニュース欄・パンくず・検索エンジン向けのデータは、プログラムが JSON から作ります。
`.html` に書くのは本文だけです。

## 本文（.html）の書き方

```html
<!-- メモはこう書く。ページには出ない -->
<section>
  <h2>見出し</h2>
  <p>段落。<strong>強調</strong>や<a href="/prefectures/gunma/">図鑑の中へのリンク</a>も書ける。</p>
  <ul>
    <li>箇条書き</li>
  </ul>
</section>

<section>
  <h2>次の見出し</h2>
  <p>……</p>
</section>
```

- `<html>` `<head>` `<body>` は書かない。本文の部分だけを書く
- 一番外側には `<section>` を並べる。`<section>` は必ず `<h2>` の見出しから始める
- 文字は `<p>` `<li>` `<td>` などの中に書く（`<section>` や `<ul>` に直接書かない）
- `<` `>` `&` を文字として書きたいときは `&lt;` `&gt;` `&amp;`

### 使えるタグ

`section` `h2` `h3` `p` `ul` `ol` `li` `a` `strong` `em` `br` `table` `thead` `tbody` `tr` `th` `td`

- 属性は `<a href="...">` の `href` だけ。`class` `style` `id` `onclick` などは書けない
  （見た目はサイトの CSS でそろえる。`id` と `class` はプログラムが付ける）
- `href` は `https://` か `/` で始める。`https://` のリンクは新しいタブで開くようにプログラムが直す

ここに無いタグ（`<script>` `<img>` `<iframe>` `<div>` `<b>` など）が入っていると、その特集はページに出ません。
このサイトはログインを扱っているので、知らない HTML を通すとログイン中の人が危なくなります（XSS）。
だから「使ってよいものだけ通す」作りにしています。

## 確かめ方

PR を出すと GitHub Actions の「Check Features」が自動で走ります。だめなところは、ログにこう出ます。

```
  NG gunma-2026-autumn.html 3行目: <b> は使えない
```

手元に Python があれば、同じ確認をこれで回せます。

```
python3 apps/scraper/features.py
```
