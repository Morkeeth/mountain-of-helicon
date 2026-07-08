"""Output-type lenses — a good next move for a React component is nothing like a
good one for a tweet or a slide. Detection is deterministic (extension + content
signals + source), mirroring the per-type dict pattern of forgetting.DEFAULT_STABILITY.
Each lens shapes the Next Move (and, later, the review dimensions) for that output.
"""
import re

# Ordered: first match wins. Each: signals + the next-prompt shape Qwen should follow.
LENSES: dict[str, dict] = {
    "frontend": {
        "ext": (".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".html"),
        "signals": (r"\breact\b", r"className=", r"<[A-Z]\w+", r"tailwind", r"useState"),
        "review_dims": ["accessibility", "responsive", "design-system", "loading/empty/error states"],
        "next_prompt_shape": "one or two VISUAL changes that reference what's on screen; "
                             "name the breakpoint or state; leave the rest of the layout alone.",
    },
    "code": {
        "ext": (".py", ".ts", ".js", ".go", ".rs", ".java", ".rb", ".c", ".cpp", ".sh"),
        "signals": (r"\bdef \b", r"\bfunction\b", r"\bclass \b", r"import ", r"=>"),
        "review_dims": ["correctness", "tests present & meaningful", "over-engineering", "duplication"],
        "next_prompt_shape": "surgical and VERIFIABLE — name the file/function, the invariant, "
                             "and the acceptance test; add a failing test first, don't touch the happy path.",
    },
    "config": {
        "ext": (".yml", ".yaml", ".toml", ".env", ".tf", ".ini", "dockerfile"),
        "signals": (r"^\s*\w+:\s", r"FROM \w+", r"export \w+="),
        "review_dims": ["correct keys/paths", "no committed secrets", "pinned versions", "least privilege"],
        "next_prompt_shape": "name the exact key, a safe default, and the blast radius; "
                             "move secrets out to a gitignored file and note the step that reads them.",
    },
    "social": {
        "ext": (),
        "signals": (r"\btweet\b", r"\bthread\b", r"\blinkedin\b", r"\bpost\b", r"#\w+", r"\bhook\b"),
        "tags": ("tweet", "x", "linkedin", "content", "post", "thread"),
        "review_dims": ["hook strength", "one idea per post", "voice (no bragging)", "length/CTA"],
        "next_prompt_shape": "hook-first and voice-locked — rewrite the opening line as the hook, "
                             "one idea per post, observer voice (no stats-bragging), platform-shaped length.",
    },
    "slides": {
        "ext": (".pptx", ".key"),
        "signals": (r"\bslide\b", r"\bdeck\b", r"\bpitch\b"),
        "review_dims": ["one idea per slide", "assertion headline", "visual evidence not bullet walls"],
        "next_prompt_shape": "one assertion per slide plus the single piece of evidence; "
                             "turn bullet walls into an assertion headline + one visual, detail to notes.",
    },
    "docs": {
        "ext": (".md", ".mdx", ".txt", ".rst"),
        "signals": (r"^#{1,3} ", r"\bREADME\b"),
        "review_dims": ["readability (~grade 9)", "sentence length", "passive voice", "leads with outcome"],
        "next_prompt_shape": "voice + audience + one structural fix — tighten to grade-9 level, "
                             "kill passive constructions, lead with the outcome not the background.",
    },
    "default": {
        "review_dims": ["relevance", "freshness", "grounding"],
        "next_prompt_shape": "a concrete, specific action grounded in the cited memory.",
    },
}


def detect_lens(title: str = "", source: str = "", source_ref: str = "", text: str = "") -> str:
    """Route an artifact to its output lens. Deterministic; 'default' if unsure."""
    ref = (source_ref or "").lower()
    blob = f"{title} {text}".lower()
    src = (source or "").lower()

    # social: source/path/tag signals (obsidian content folders, taste-machine)
    if any(k in ref or k in src for k in ("02 content", "taste-machine", "/content", "tweet", "linkedin")):
        return "social"

    for kind, spec in LENSES.items():
        if kind == "default":
            continue
        if any(ref.endswith(e) or e in ref for e in spec.get("ext", ())):
            return kind
    for kind, spec in LENSES.items():
        if kind == "default":
            continue
        if any(re.search(p, blob, re.MULTILINE) for p in spec.get("signals", ())):
            return kind
    return "default"


def lens_guidance(kinds: set[str]) -> str:
    """A prompt block describing the next-move shape for exactly the lenses present."""
    kinds = {k for k in kinds if k in LENSES} or {"default"}
    lines = [f"- {k}: {LENSES[k]['next_prompt_shape']}" for k in sorted(kinds)]
    return ("Shape each move to the output type of the memory it addresses:\n" + "\n".join(lines))
