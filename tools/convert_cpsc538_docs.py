from pathlib import Path
import html
import re


ROOT = Path(__file__).resolve().parents[1]
DOCS = [
    ("Other Media/CPSC538G/SRP/design_SRP.md", "SRP Design Notes"),
    ("Other Media/CPSC538G/SRP/testing_SRP.md", "SRP Testing Notes"),
    ("Other Media/CPSC538G/CBS/design_CBS.md", "CBS Design Notes"),
    ("Other Media/CPSC538G/CBS/testing_CBS.md", "CBS Testing Notes"),
]


def slugify(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text or "section"


def inline(text):
    text = html.escape(text, quote=False)
    text = re.sub(r"&lt;br&gt;", "<br>", text)
    text = re.sub(r"&lt;b&gt;(.*?)&lt;/b&gt;", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", lambda m: f"<code>{html.escape(m.group(1))}</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    text = re.sub(r"\$\$([^$]+)\$\$", r'<span class="math-inline">\( \1 \)</span>', text)
    text = re.sub(r"\$([^$\n]+)\$", r'<span class="math-inline">\( \1 \)</span>', text)
    return text


def render_table(rows):
    align = []
    if len(rows) > 1 and all(set(cell.strip()) <= set(":- ") for cell in rows[1]):
        for cell in rows[1]:
            stripped = cell.strip()
            if stripped.startswith(":") and stripped.endswith(":"):
                align.append("center")
            elif stripped.endswith(":"):
                align.append("right")
            else:
                align.append("left")
        body_rows = rows[2:]
    else:
        align = ["left"] * len(rows[0])
        body_rows = rows[1:]

    def attrs(index):
        return f' style="text-align: {align[index]};"' if index < len(align) else ""

    header = "".join(
        f"<th{attrs(index)}>{inline(cell.strip())}</th>"
        for index, cell in enumerate(rows[0])
    )
    body = []
    for row in body_rows:
        cells = "".join(
            f"<td{attrs(index)}>{inline(cell.strip())}</td>"
            for index, cell in enumerate(row)
        )
        body.append(f"<tr>{cells}</tr>")

    return (
        '<div class="table-wrap"><table>'
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody>"
        "</table></div>"
    )


def split_table_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_markdown(markdown):
    lines = markdown.replace("\r\n", "\n").split("\n")
    html_lines = []
    toc = []
    paragraph = []
    list_stack = []
    in_code = False
    code_lines = []
    code_lang = ""
    i = 0

    def close_paragraph():
        nonlocal paragraph
        if paragraph:
            html_lines.append(f"<p>{inline(' '.join(paragraph).strip())}</p>")
            paragraph = []

    def close_lists(to_indent=-1):
        while list_stack and list_stack[-1][0] > to_indent:
            _, tag = list_stack.pop()
            html_lines.append(f"</{tag}>")

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if in_code:
            if stripped.startswith("```"):
                html_lines.append(
                    f'<pre><code class="language-{html.escape(code_lang)}">'
                    f"{html.escape(chr(10).join(code_lines))}</code></pre>"
                )
                in_code = False
                code_lines = []
                code_lang = ""
            else:
                code_lines.append(line)
            i += 1
            continue

        if stripped.startswith("```"):
            close_paragraph()
            close_lists()
            in_code = True
            code_lang = stripped[3:].strip()
            i += 1
            continue

        if not stripped:
            close_paragraph()
            close_lists()
            i += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            close_paragraph()
            close_lists()
            level = len(heading.group(1))
            text = heading.group(2).strip()
            slug = slugify(text)
            toc.append((level, slug, re.sub(r"<[^>]+>", "", text)))
            html_lines.append(f'<h{level} id="{slug}">{inline(text)}</h{level}>')
            i += 1
            continue

        if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4:
            close_paragraph()
            close_lists()
            html_lines.append(f'<div class="math-block">\\[{html.escape(stripped[2:-2].strip())}\\]</div>')
            i += 1
            continue

        if stripped.startswith("|") and "|" in stripped[1:]:
            close_paragraph()
            close_lists()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_table_row(lines[i]))
                i += 1
            html_lines.append(render_table(rows))
            continue

        image = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image:
            close_paragraph()
            close_lists()
            alt = image.group(1).strip() or "Documentation screenshot"
            src = image.group(2).strip()
            html_lines.append(
                '<figure class="doc-figure">'
                f'<a href="{html.escape(src)}" target="_blank">'
                f'<img src="{html.escape(src)}" alt="{html.escape(alt)}" />'
                "</a>"
                f"<figcaption>{html.escape(alt)}</figcaption>"
                "</figure>"
            )
            i += 1
            continue

        bullet = re.match(r"^(\s*)([-*]|\d+\.)\s+(.+)$", line)
        if bullet:
            close_paragraph()
            indent = len(bullet.group(1))
            tag = "ol" if bullet.group(2).endswith(".") else "ul"
            if not list_stack or indent > list_stack[-1][0]:
                html_lines.append(f"<{tag}>")
                list_stack.append((indent, tag))
            else:
                close_lists(indent)
                if not list_stack or list_stack[-1][1] != tag:
                    close_lists(indent - 1)
                    html_lines.append(f"<{tag}>")
                    list_stack.append((indent, tag))
            html_lines.append(f"<li>{inline(bullet.group(3).strip())}</li>")
            i += 1
            continue

        paragraph.append(stripped)
        i += 1

    close_paragraph()
    close_lists()
    return toc, "\n".join(html_lines)


def render_page(title, source_name, body, toc):
    toc_items = "\n".join(
        f'<a class="toc-level-{level}" href="#{slug}">{html.escape(text)}</a>'
        for level, slug, text in toc
        if level <= 3
    )
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet" />
    <script>
      window.MathJax = {{
        tex: {{ inlineMath: [['\\\\(', '\\\\)']], displayMath: [['\\\\[', '\\\\]']] }},
        svg: {{ fontCache: 'global' }}
      }};
    </script>
    <script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
    <style>
      :root {{
        --bg: #f8f9fb;
        --paper: #ffffff;
        --text: #23252f;
        --muted: #676d7c;
        --line: #dfe3ec;
        --accent: #297373;
        --accent-soft: #e8f4f3;
        --code-bg: #f3f5f8;
      }}

      * {{
        box-sizing: border-box;
      }}

      body {{
        margin: 0;
        background: var(--bg);
        color: var(--text);
        font-family: 'Poppins', sans-serif;
        line-height: 1.65;
      }}

      .doc-shell {{
        width: min(1180px, calc(100% - 32px));
        margin: 0 auto;
        padding: 32px 0 56px;
      }}

      .doc-header {{
        margin-bottom: 24px;
      }}

      .back-link,
      .source-link {{
        color: var(--accent);
        font-weight: 600;
        text-decoration: none;
      }}

      .back-link:hover,
      .source-link:hover,
      .toc a:hover {{
        text-decoration: underline;
      }}

      .doc-layout {{
        display: grid;
        grid-template-columns: minmax(0, 1fr) 260px;
        gap: 28px;
        align-items: start;
      }}

      article {{
        min-width: 0;
        background: var(--paper);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: clamp(20px, 4vw, 42px);
        box-shadow: 0 12px 32px rgba(28, 33, 45, 0.08);
      }}

      .toc {{
        position: sticky;
        top: 20px;
        background: var(--paper);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 18px;
      }}

      .toc-title {{
        margin: 0 0 10px;
        font-size: 0.85rem;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }}

      .toc a {{
        display: block;
        color: var(--text);
        font-size: 0.9rem;
        line-height: 1.35;
        margin: 8px 0;
        text-decoration: none;
      }}

      .toc-level-3 {{
        padding-left: 14px;
        color: var(--muted) !important;
        font-size: 0.82rem !important;
      }}

      h1,
      h2,
      h3,
      h4 {{
        line-height: 1.2;
        margin: 1.6em 0 0.55em;
      }}

      h1 {{
        margin-top: 0;
        font-size: clamp(2rem, 5vw, 3.2rem);
      }}

      h2 {{
        border-top: 1px solid var(--line);
        padding-top: 1em;
        font-size: clamp(1.4rem, 3vw, 2rem);
      }}

      h3 {{
        font-size: 1.15rem;
      }}

      p {{
        margin: 0.8em 0;
      }}

      ul,
      ol {{
        padding-left: 1.4rem;
      }}

      li {{
        margin: 0.45rem 0;
      }}

      code {{
        background: var(--code-bg);
        border: 1px solid var(--line);
        border-radius: 4px;
        padding: 0.1rem 0.35rem;
        font-family: Consolas, 'Courier New', monospace;
        font-size: 0.92em;
      }}

      pre {{
        overflow-x: auto;
        background: #18202a;
        color: #eef4f8;
        border-radius: 8px;
        padding: 18px;
      }}

      pre code {{
        background: transparent;
        border: 0;
        color: inherit;
        padding: 0;
      }}

      .table-wrap {{
        overflow-x: auto;
        margin: 1rem 0 1.4rem;
      }}

      table {{
        width: 100%;
        border-collapse: collapse;
        background: var(--paper);
      }}

      th,
      td {{
        border: 1px solid var(--line);
        padding: 0.65rem 0.8rem;
        vertical-align: top;
      }}

      th {{
        background: var(--accent-soft);
      }}

      .doc-figure {{
        margin: 1.6rem 0;
      }}

      .doc-figure img {{
        display: block;
        width: 100%;
        max-height: 760px;
        object-fit: contain;
        background: white;
        border: 1px solid var(--line);
        border-radius: 6px;
        box-shadow: 0 8px 24px rgba(28, 33, 45, 0.12);
      }}

      figcaption {{
        color: var(--muted);
        font-size: 0.9rem;
        margin-top: 0.55rem;
        text-align: center;
      }}

      .math-block {{
        overflow-x: auto;
        background: var(--accent-soft);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 0.8rem 1rem;
        margin: 1rem 0;
      }}

      @media (max-width: 900px) {{
        .doc-layout {{
          grid-template-columns: 1fr;
        }}

        .toc {{
          position: static;
          order: -1;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="doc-shell">
      <header class="doc-header">
        <a class="back-link" href="../../../Other%20Projects/RTOS%20Scheduling%20Algorithms.html">&larr; Back to RTOS Scheduling Algorithms</a>
      </header>
      <div class="doc-layout">
        <article>
          {body}
          <p><a class="source-link" href="{html.escape(source_name)}">Open original markdown</a></p>
        </article>
        <nav class="toc" aria-label="Table of contents">
          <p class="toc-title">On This Page</p>
          {toc_items}
        </nav>
      </div>
    </main>
  </body>
</html>
"""


def main():
    for relative_path, title in DOCS:
        source = ROOT / relative_path
        markdown = source.read_text(encoding="utf-8")
        toc, body = parse_markdown(markdown)
        output = source.with_suffix(".html")
        with output.open("w", encoding="utf-8", newline="\n") as html_file:
            html_file.write(render_page(title, source.name, body, toc))
        print(f"Wrote {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
