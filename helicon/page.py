"""One HTML page for a human: the grade, the three worst problems, a copyable fix."""
from __future__ import annotations

import html
import os

from helicon.fix import plan_fixes

_TIER_RANK = {"version": 0, "command": 1, "pointer": 2, "execution": 3}


def worst_three(findings: list[dict]) -> list[dict]:
    ranked = sorted(enumerate(findings), key=lambda pair: (_TIER_RANK.get(pair[1].get("tier"), 9), pair[0]))
    return [item for _, item in ranked[:3]]


def _copy_text(repo_name: str, finding: dict, replacement: str | None) -> str:
    where = finding.get("where") or "the instruction file"
    raw = finding.get("raw") or ""
    if replacement:
        return f"In {where}, change {raw} to {replacement}"
    return f"In {where}, {raw} is not in {repo_name}. No single file matches, so correct it by hand."


def render_page(repo_root: str, summary: dict | None = None, fixes: list[dict] | None = None) -> str:
    if summary is None:
        from helicon.review import review, review_summary
        summary = review_summary(repo_root, review(repo_root))
    name = os.path.basename(os.path.abspath(repo_root).rstrip("/")) or repo_root
    grade = summary.get("grade") or "-"
    broken = int(summary.get("broken") or 0)
    checked = int(summary.get("checked") or 0)
    if fixes is None:
        fix_rows = plan_fixes(repo_root)
    elif isinstance(fixes, dict):
        fix_rows = fixes.get("safe") or []
    else:
        fix_rows = fixes
    by_raw = {row["raw"]: row["replacement"] for row in fix_rows}
    problems = []
    for finding in worst_three(summary.get("findings") or []):
        raw = finding.get("raw") or ""
        problems.append((finding, by_raw.get(raw)))

    if checked == 0:
        lead = "No checkable claim in the instruction files."
    elif broken == 0:
        lead = f"{checked} claims checked. None contradicted."
    else:
        lead = f"{checked} claims checked. {broken} contradicted."

    rows = []
    if not problems:
        rows.append("<p class='quiet'>Nothing to fix on this page.</p>")
    for finding, replacement in problems:
        where = html.escape(finding.get("where") or "")
        raw = html.escape(finding.get("raw") or "")
        detail = html.escape(finding.get("detail") or "")
        copy = html.escape(_copy_text(name, finding, replacement), quote=True)
        if replacement:
            action = f"Change it to <code>{html.escape(replacement)}</code>"
        else:
            action = "No single matching file. Correct this by hand."
        rows.append(
            "<article>"
            f"<p class='where'>{where}</p>"
            f"<p class='claim'>{raw}</p>"
            f"<p class='detail'>{detail}</p>"
            f"<p class='action'>{action}</p>"
            f"<button type='button' data-copy=\"{copy}\">Copy the fix</button>"
            "</article>"
        )

    more = max(0, len(summary.get("findings") or []) - len(problems))
    more_line = f"<p class='quiet'>{more} more in the terminal review.</p>" if more else ""
    if not problems:
        heading = "Nothing contradicted"
    elif len(problems) == 1:
        heading = "The worst"
    else:
        heading = f"The {len(problems)} worst"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Helicon {html.escape(name)} {html.escape(str(grade))}</title>
<style>
  :root {{
    --ink: #17283A;
    --paper: #ECE4D8;
    --card: #F4EFE7;
    --slate: #4E6173;
    --navy: #223A4E;
    --line: rgba(23, 40, 58, 0.16);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: "Bricolage Grotesque", "Avenir Next", "Segoe UI", sans-serif;
    padding: 48px 28px 80px;
  }}
  main {{ max-width: 40rem; }}
  .mark {{
    margin: 0;
    font-size: 0.8rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }}
  .grade {{
    margin: 0.1rem 0 0;
    font-family: Fraunces, "Iowan Old Style", Palatino, serif;
    font-size: 9rem;
    line-height: 0.8;
    font-weight: 560;
    letter-spacing: -0.04em;
  }}
  .lead {{ font-size: 1.25rem; margin: 0.6rem 0 1.6rem; }}
  h2 {{ font-size: 1rem; margin: 0 0 0.8rem; font-weight: 600; }}
  article {{
    border-top: 1px solid var(--line);
    padding: 0.9rem 0 1rem;
  }}
  .where {{ margin: 0; font-family: "IBM Plex Mono", "SF Mono", ui-monospace, monospace; font-size: 0.85rem; }}
  .claim {{ margin: 0.35rem 0 0; font-size: 1.35rem; font-weight: 650; }}
  .detail, .action, .quiet {{ margin: 0.3rem 0 0; color: var(--slate); }}
  button {{
    margin-top: 0.7rem;
    background: var(--navy);
    color: var(--card);
    border: 0;
    padding: 0.55rem 0.8rem;
    font: inherit;
    font-size: 0.95rem;
    cursor: pointer;
  }}
  button.done {{ background: var(--ink); }}
</style>
</head>
<body>
<main>
  <p class="mark">Helicon, {html.escape(name)}</p>
  <p class="grade">{html.escape(str(grade))}</p>
  <p class="lead">{html.escape(lead)}</p>
  <h2>{html.escape(heading)}</h2>
  {''.join(rows)}
  {more_line}
</main>
<script>
  document.querySelectorAll("button[data-copy]").forEach(function (btn) {{
    btn.addEventListener("click", function () {{
      var text = btn.getAttribute("data-copy");
      function copied() {{
        btn.textContent = "Copied";
        btn.classList.add("done");
      }}
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(text).then(copied).catch(function () {{
          var area = document.createElement("textarea");
          area.value = text;
          document.body.appendChild(area);
          area.select();
          document.execCommand("copy");
          area.remove();
          copied();
        }});
      }}
    }});
  }});
</script>
</body>
</html>
"""


def write_page(repo_root: str, summary: dict, path: str) -> str:
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_page(repo_root, summary))
    return path
