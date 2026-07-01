"""Task Playbooks: mine review patterns + feedback into category-specific guidance.

Each playbook answers: "when doing X, what has the user corrected before, what
tone/style works, what mistakes to avoid?" This is the 'increasingly accurate
decisions' part of the MemoryAgent spec.

TASK_CATEGORIES below is a generic default shipped with the tool. Categories are
matched to a task by keyword; feedback_keys are search hints used to pull relevant
lessons from the user's OWN memory cubes at runtime. Nothing here is user-specific.
"""

import json
import sqlite3
from datetime import datetime


# Generic defaults. feedback_keys are plain search terms matched against the user's
# own memory cubes at runtime - not references to any specific person's notes.
TASK_CATEGORIES = {
    "build": {
        "label": "Building / Shipping Code",
        "tags": ["code", "build", "ship", "feature", "deploy", "refactor", "bug", "test"],
        "feedback_keys": [
            "scope", "shipping", "testing", "fake data", "not done", "cautious",
        ],
    },
    "content": {
        "label": "Content / Writing / Voice",
        "tags": ["content", "draft", "twitter", "linkedin", "article", "tweet", "write", "post", "publish"],
        "feedback_keys": [
            "hooks", "voice", "quality", "timing", "hype", "tone",
        ],
    },
    "design": {
        "label": "Design / UI / UX",
        "tags": ["design", "ui", "frontend", "dashboard", "ux", "layout"],
        "feedback_keys": [
            "ui", "design", "quality",
        ],
    },
    "audit": {
        "label": "Audit / Review / Strategy",
        "tags": ["audit", "review", "strategy", "analysis", "evaluate", "check"],
        "feedback_keys": [
            "critical", "validation", "strategy", "review",
        ],
    },
    "context": {
        "label": "Context / Memory / Organization",
        "tags": ["memory", "context", "notes", "organize", "save", "docs"],
        "feedback_keys": [
            "context", "memory", "organization", "efficiency",
        ],
    },
    "research": {
        "label": "Research / Planning",
        "tags": ["research", "plan", "explore", "investigate", "compare"],
        "feedback_keys": [
            "research", "planning", "scope",
        ],
    },
}


def init_playbooks_table(conn: sqlite3.Connection):
    conn.execute("""CREATE TABLE IF NOT EXISTS playbooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        label TEXT NOT NULL,
        feedback_rules TEXT NOT NULL,
        review_stats TEXT,
        prompt_template TEXT,
        updated_at TEXT NOT NULL,
        usage_count INTEGER DEFAULT 0
    )""")
    conn.commit()


def _get_feedback_from_cubes(conn: sqlite3.Connection, keys: list[str]) -> list[dict]:
    """Find memory cubes that match feedback keys."""
    feedback = []
    for key in keys:
        search_term = key.replace("_", " ")
        rows = conn.execute(
            "SELECT id, title, content, confidence FROM glaze_cubes "
            "WHERE type = 'memory' AND (title LIKE ? OR content LIKE ?) "
            "AND review_status != 'killed' AND merged_into IS NULL "
            "LIMIT 2",
            (f"%{search_term}%", f"%{search_term}%"),
        ).fetchall()
        for r in rows:
            content = (r["content"] or "")[:300]
            if content:
                feedback.append({
                    "key": key,
                    "title": r["title"],
                    "rule": content,
                    "confidence": r["confidence"],
                })

    return feedback


def _get_review_stats_for_category(conn: sqlite3.Connection, tags: list[str]) -> dict:
    """Get review patterns for cubes matching category tags."""
    placeholders = ",".join("?" * len(tags))
    like_clauses = " OR ".join(f"tags LIKE ?" for _ in tags)
    params = [f"%{t}%" for t in tags]

    total = conn.execute(
        f"SELECT COUNT(*) FROM glaze_cubes WHERE ({like_clauses}) AND merged_into IS NULL",
        params,
    ).fetchone()[0]

    reviewed = conn.execute(
        f"SELECT COUNT(*) FROM glaze_cubes WHERE ({like_clauses}) "
        f"AND review_status IN ('approved','revised','killed') AND merged_into IS NULL",
        params,
    ).fetchone()[0]

    approved = conn.execute(
        f"SELECT COUNT(*) FROM glaze_cubes WHERE ({like_clauses}) "
        f"AND review_status = 'approved' AND merged_into IS NULL",
        params,
    ).fetchone()[0]

    killed = conn.execute(
        f"SELECT COUNT(*) FROM glaze_cubes WHERE ({like_clauses}) "
        f"AND review_status = 'killed' AND merged_into IS NULL",
        params,
    ).fetchone()[0]

    return {
        "total_cubes": total,
        "reviewed": reviewed,
        "approved": approved,
        "killed": killed,
        "ship_rate": round(approved / reviewed, 3) if reviewed > 0 else 0,
        "kill_rate": round(killed / reviewed, 3) if reviewed > 0 else 0,
    }


def _generate_prompt_template(category: str, label: str, feedback: list[dict], stats: dict) -> str:
    """Generate a ready-to-use prompt template for this task category."""
    rules = []
    for f in feedback[:8]:
        rule_text = f["rule"].split("\n")[0].strip()
        if len(rule_text) > 20:
            rules.append(f"- {rule_text}")

    rules_block = "\n".join(rules) if rules else "- No specific rules yet. Review more items to build patterns."

    stat_line = ""
    if stats["reviewed"] > 0:
        stat_line = f"Historical: {stats['ship_rate']:.0%} ship rate, {stats['kill_rate']:.0%} kill rate across {stats['reviewed']} reviewed items."

    return f"""## {label} Playbook

### Context
{stat_line}

### Rules (from review history)
{rules_block}

### Template
When working on {label.lower()} tasks, apply these rules from prior sessions.
If unsure about a decision, check glaze_context for relevant memories before proceeding.
"""


def build_playbooks(conn: sqlite3.Connection) -> list[dict]:
    """Build all task playbooks from review data + feedback patterns."""
    init_playbooks_table(conn)

    now = datetime.utcnow().isoformat()
    results = []

    conn.execute("DELETE FROM playbooks")

    for cat_key, cat in TASK_CATEGORIES.items():
        feedback = _get_feedback_from_cubes(conn, cat["feedback_keys"])
        stats = _get_review_stats_for_category(conn, cat["tags"])
        template = _generate_prompt_template(cat_key, cat["label"], feedback, stats)

        feedback_json = json.dumps([{
            "key": f["key"],
            "title": f["title"],
            "rule": f["rule"][:200],
        } for f in feedback])

        conn.execute(
            "INSERT INTO playbooks (category, label, feedback_rules, review_stats, "
            "prompt_template, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cat_key, cat["label"], feedback_json,
             json.dumps(stats), template, now),
        )

        results.append({
            "category": cat_key,
            "label": cat["label"],
            "feedback_count": len(feedback),
            "review_stats": stats,
            "prompt_template": template,
        })

    conn.commit()
    return results


def get_playbooks(conn: sqlite3.Connection) -> list[dict]:
    init_playbooks_table(conn)
    rows = conn.execute(
        "SELECT category, label, feedback_rules, review_stats, "
        "prompt_template, updated_at, usage_count FROM playbooks "
        "ORDER BY usage_count DESC"
    ).fetchall()

    results = []
    for r in rows:
        results.append({
            "category": r["category"],
            "label": r["label"],
            "feedback_rules": json.loads(r["feedback_rules"]),
            "review_stats": json.loads(r["review_stats"]),
            "prompt_template": r["prompt_template"],
            "updated_at": r["updated_at"],
            "usage_count": r["usage_count"],
        })
    return results


def get_playbook_for_task(conn: sqlite3.Connection, task_description: str) -> dict | None:
    """Match a task description to the best playbook. Returns the playbook + relevant feedback."""
    init_playbooks_table(conn)
    task_words = set(task_description.lower().split())

    best_match = None
    best_score = 0

    for cat_key, cat in TASK_CATEGORIES.items():
        score = sum(1 for tag in cat["tags"] if tag in task_words)
        label_words = [w for w in cat["label"].lower().split() if len(w) > 2]
        score += sum(2 for w in label_words if w in task_words)

        if score > best_score:
            best_score = score
            best_match = cat_key

    if not best_match or best_score == 0:
        return None

    row = conn.execute(
        "SELECT * FROM playbooks WHERE category = ?", (best_match,)
    ).fetchone()

    if row:
        conn.execute(
            "UPDATE playbooks SET usage_count = usage_count + 1 WHERE category = ?",
            (best_match,),
        )
        conn.commit()
        return {
            "category": row["category"],
            "label": row["label"],
            "feedback_rules": json.loads(row["feedback_rules"]),
            "review_stats": json.loads(row["review_stats"]),
            "prompt_template": row["prompt_template"],
        }

    return None
