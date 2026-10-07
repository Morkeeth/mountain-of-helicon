"""The `helicon start` card as one local page.

One file, no network: the brand faces are embedded when the repo's font files are
present, and the page falls back to system faces when they are not. Nothing here
measures anything; it draws the card `helicon.start.build_card` already made.

Colour: ink navy and its lighter and brighter blues only (Oscar, 7 Oct 2026: all blue
in different nuances, no other colour, less beige).

The one device: each reading is a measuring strip, drawn to scale. Four stale files
of 390 is a notch you can barely see, and that is the point. Where a total would go
there is an empty slot that says why it is empty.
"""

import base64
import html
import os
from datetime import datetime

_FONTS = (
    ("Fraunces", "300 900", "Fraunces-latin.woff2"),
    ("Bricolage Grotesque", "400 700", "BricolageGrotesque-latin.woff2"),
    ("IBM Plex Mono", "400", "IBMPlexMono-400-latin.woff2"),
)


def _font_faces():
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "public", "fonts")
    faces = []
    for family, weight, name in _FONTS:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as handle:
            data = base64.b64encode(handle.read()).decode("ascii")
        faces.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};font-display:swap;"
            f"src:url(data:font/woff2;base64,{data}) format('woff2')}}"
        )
    return "".join(faces)


CSS = """
:root{--paper:#EDF1F6;--sheet:#F7F9FC;--ink:#17283A;--slate:#42586E;--mist:#6F8296;
--rule:rgba(23,40,58,.16);--track:#D5DEE8;--mark:#2B5F9E}
@media (prefers-color-scheme:dark){:root{--paper:#0E1A27;--sheet:#152535;--ink:#E6EDF5;
--slate:#A9BCCF;--mist:#7E93A8;--rule:rgba(230,237,245,.18);--track:#22384E;--mark:#7FB0E6}}
*{box-sizing:border-box}
html{background:var(--paper)}
body{margin:0;color:var(--ink);font-family:'Bricolage Grotesque',system-ui,sans-serif;font-size:17px;line-height:1.45;
-webkit-font-smoothing:antialiased}
main{max-width:1040px;margin:0 auto;padding:56px 32px 72px}
header{display:flex;justify-content:space-between;align-items:baseline;gap:24px;flex-wrap:wrap;
border-bottom:2px solid var(--ink);padding-bottom:18px}
h1{font-family:'Fraunces',Georgia,serif;font-weight:560;font-size:44px;letter-spacing:-.02em;line-height:1;margin:0}
.sub{color:var(--slate);margin:6px 0 0}
.when{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13px;color:var(--mist);text-align:right}
.from{display:grid;grid-template-columns:150px 1fr;gap:8px 24px;padding:18px 0;border-bottom:1px solid var(--rule);
font-size:15px}
.from b{font-weight:600}
.path{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13px;color:var(--slate);overflow-wrap:anywhere}
.status{margin:0;padding:16px 0;border-bottom:1px solid var(--rule);color:var(--slate)}
.status.stale{color:var(--mark);font-weight:600}
details{margin-top:36px;color:var(--mist);font-size:14px}summary{cursor:pointer}
details ul{margin:10px 0 0;padding-left:18px;font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12.5px;overflow-wrap:anywhere}
.row{display:grid;grid-template-columns:150px minmax(0,300px) 1fr;gap:10px 24px;align-items:end;
padding:26px 0 22px;border-bottom:1px solid var(--rule)}
.label{font-weight:600;font-size:15px;align-self:start;padding-top:10px}
.num{font-family:'Fraunces',Georgia,serif;font-weight:420;font-size:54px;line-height:.95;letter-spacing:-.025em;
font-variant-numeric:tabular-nums}
.num small{font-size:21px;font-weight:400;letter-spacing:0;color:var(--slate);margin-left:6px}
.say{color:var(--slate);font-size:16px;padding-bottom:6px}
.none{font-family:'Fraunces',Georgia,serif;font-style:italic;font-size:24px;color:var(--mist)}
.strip{grid-column:2 / 4;height:14px;background:var(--track);position:relative;margin-top:4px}
.strip i{position:absolute;inset:0 auto 0 0;background:var(--mark);min-width:3px}
.read{grid-column:2 / 4}
.total{display:grid;grid-template-columns:150px 1fr;gap:10px 24px;padding:22px 0;border-bottom:2px solid var(--ink)}
.slot{border:1px dashed var(--rule);padding:14px 18px;color:var(--mist);font-size:15px}
h2{font-family:'Fraunces',Georgia,serif;font-weight:520;font-size:28px;letter-spacing:-.01em;margin:44px 0 8px}
ol{margin:0;padding:0;list-style:none;counter-reset:n}
ol li{counter-increment:n;display:grid;grid-template-columns:150px 1fr;gap:6px 24px;padding:16px 0;
border-bottom:1px solid var(--rule)}
ol li::before{content:counter(n);font-family:'Fraunces',Georgia,serif;font-size:30px;line-height:1;color:var(--mark)}
ol li code{display:block;margin-top:6px}
code{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13px;color:var(--slate);overflow-wrap:anywhere}
footer{margin-top:40px;color:var(--mist);font-size:14px}
@media (max-width:720px){main{padding:32px 18px 48px}h1{font-size:34px}.when{text-align:left}
.from,.row,.total,ol li{grid-template-columns:1fr;gap:6px}.label{padding-top:0}.num{font-size:44px}
.strip,.read{grid-column:1}}
"""


def _strip(part, whole):
    if not whole:
        return ""
    share = max(0.0, min(1.0, part / whole))
    fill = f'<i style="width:{share * 100:.2f}%"></i>' if part else ""  # zero draws nothing, not a sliver
    return f'<div class="strip" role="img" aria-label="{part} of {whole}">{fill}</div>'


def _day(iso):
    """2026-10-07 as 7 Oct 2026. Anything else is returned as it came."""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%-d %b %Y")
    except (TypeError, ValueError):
        return iso or ""


def _count(value):
    return f"{value:,}" if isinstance(value, int) else value


def _row(row):
    esc = html.escape
    if not row["found"]:
        body = f'<div class="none">nothing found</div><div class="say">{esc(row["text"])}</div>'
        return f'<section class="row"><div class="label">{esc(row["label"])}</div>{body}</section>'
    strip = _strip(row["part"], row["whole"]) if row["whole"] else ""
    return (
        f'<section class="row"><div class="label">{esc(row["label"])}</div>'
        f'<div class="num">{esc(str(_count(row["number"])))}<small>{esc(row["unit"])}</small></div>'
        f'<div class="say">{esc(row["text"])}</div>{strip}</section>'
    )


def render(card, when=None):
    from helicon.start import plain

    esc = html.escape
    when = when or datetime.now().astimezone()
    view = plain(card)
    sentence, problem = view["status"]
    status = f'<p class="status{" stale" if problem else ""}">{esc(sentence)}</p>' if sentence else ""

    if view["steps"]:
        items = "".join(
            f"<li><div>{esc(text)}</div></li>" for text, _ in view["steps"])
        steps = f"<h2>Do next</h2><ol>{items}</ol>"
    else:
        steps = "<h2>Do next</h2><p class='sub'>Nothing to fix was found in what could be read.</p>"

    sources = "".join(f"<li>{esc(row['label'])}: {esc(row['detail'])}</li>" for row in view["rows"] if row.get("detail"))
    sources += "".join(f"<li>To do step {n}: {esc(command)}</li>"
                       for n, (_, command) in enumerate(view["steps"], 1) if command)
    inst = card.get("install") or {}
    if inst.get("read"):
        sources += f"<li>Helicon itself: {esc(inst['read'])}" + (f", branch {esc(inst.get('branch', ''))}" if inst.get("git") else "") + "</li>"
    details = f"<details><summary>Where these numbers come from, and the commands</summary><ul>{sources}</ul></details>" if sources else ""

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Helicon</title><style>{_font_faces()}{CSS}</style></head><body><main>"
        "<header><div><h1>Helicon</h1><p class='sub'>Where your context is, and its state.</p></div>"
        f"<div class='when'>{esc(when.strftime('%-d %b %Y, %H:%M'))}</div></header>"
        f"{status}{''.join(_row(row) for row in view['rows'])}"
        "<div class='total'><div class='label'>Total</div><div class='slot'>No total. These five readings "
        "measure different things, so they are not added up.</div></div>"
        f"{steps}{details}"
        "<footer>Nothing was changed. This page is a file on this Mac.</footer>"
        "</main></body></html>"
    )
