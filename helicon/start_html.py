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
.stale{color:var(--mark);font-weight:600}
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


def _row(label, part, number, unit, sentence, strip="", read=""):
    esc = html.escape
    if not part.get("found"):
        body = f'<div class="none">nothing found</div><div class="say">{esc(part.get("why", ""))}</div>'
        return f'<section class="row"><div class="label">{esc(label)}</div>{body}</section>'
    source = f'<div class="path read">read from {esc(str(read))}</div>' if read else ""
    return (
        f'<section class="row"><div class="label">{esc(label)}</div>'
        f'<div class="num">{esc(str(_count(number)))}<small>{esc(unit)}</small></div>'
        f'<div class="say">{esc(sentence)}</div>{strip}{source}</section>'
    )


def render(card, when=None):
    esc = html.escape
    when = when or datetime.now().astimezone()
    ins, mem, dec, ski, idx = (card[k] for k in ("instructions", "memory", "decisions", "skills", "index"))
    inst = card.get("install") or {}

    if inst.get("git"):
        behind = inst.get("behind_main")
        if behind is None:
            state = "distance to main unknown"
        elif behind == 0:
            state = "up to date with main"
        else:
            state = f'<span class="stale">stale: {behind} commit(s) behind main</span>'
        running = (f'<div class="from"><b>Running from</b><div><div class="path">{esc(inst["read"])}</div>'
                   f'<div>branch {esc(inst.get("branch", ""))} · {state}</div></div></div>')
    elif inst:
        running = (f'<div class="from"><b>Running from</b><div><div class="path">{esc(inst["read"])}</div>'
                   f"<div>an installed copy, not a git tree</div></div></div>")
    else:
        running = ""

    rows = [
        _row("Instructions", ins, ins.get("broken"), f"of {ins.get('checked')}",
             f"checked lines do not match the repo. Grade {ins.get('grade')}.",
             _strip(ins.get("broken") or 0, ins.get("checked") or 0), ins.get("read")),
        _row("Memory", mem, mem.get("rotten"), f"of {mem.get('files')}",
             "memory files carry a stale or expired claim.",
             _strip(mem.get("rotten") or 0, mem.get("files") or 0), ", ".join(mem.get("read", []))),
        _row("Decisions", dec, dec.get("rulings"), "rulings",
             f"on record in your own words. Newest {_day(dec.get('newest'))}.", "", dec.get("read")),
    ]
    if ski.get("found") and ski.get("opened_known"):
        rows.append(_row("Skills", ski, ski["never_opened"], f"of {ski['installed']}",
                         "installed skills were never opened in your indexed sessions.",
                         _strip(ski["never_opened"], ski["installed"]), ski.get("read")))
    else:
        rows.append(_row("Skills", ski, ski.get("installed"), "installed", ski.get("why", "")))
    warned = idx.get("files_with_warnings")
    rows.append(_row("Index", idx, idx.get("sessions"), "sessions",
                     f"indexed. Newest {_day(idx.get('newest'))}."
                     + (f" {warned} file(s) carry a warning." if warned else ""), "", idx.get("read")))

    if card.get("next"):
        items = []
        for step in card["next"]:
            text, _, command = step.partition(": helicon ")
            code = f"<code>helicon {esc(command)}</code>" if command else ""
            items.append(f"<li><div>{esc(text if command else step)}{code}</div></li>")
        steps = f"<h2>Do next</h2><ol>{''.join(items)}</ol>"
    else:
        steps = "<h2>Do next</h2><p class='sub'>Nothing to fix was found in what could be read.</p>"

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Helicon start</title><style>{_font_faces()}{CSS}</style></head><body><main>"
        "<header><div><h1>Helicon</h1><p class='sub'>Where your context is, and its state.</p></div>"
        f"<div class='when'>read {esc(when.strftime('%d %b %Y, %H:%M'))}<br>helicon start</div></header>"
        f"{running}{''.join(rows)}"
        "<div class='total'><div class='label'>Total</div><div class='slot'>No total. These five readings "
        "measure different things, so they are not added up.</div></div>"
        f"{steps}"
        "<footer>Read only. This page is a local file and was made on this machine.</footer>"
        "</main></body></html>"
    )
