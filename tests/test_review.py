import sys, os, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from helicon.review import review, format_review

def _repo(files):
    d = tempfile.mkdtemp()
    for r,b in files.items():
        p=os.path.join(d,r); os.makedirs(os.path.dirname(p),exist_ok=True) if os.path.dirname(p) else None
        open(p,"w").write(b)
    return d

def test_review_flags_a_lying_setup():
    d=_repo({"run.py":"x","CLAUDE.md":"Read `docs/MISSING.md`.\n"})
    out=format_review(d, review(d))
    assert "lies to its agent" in out and "MISSING.md" in out and "Based on:" in out

def test_review_passes_a_clean_setup():
    d=_repo({"package.json":json.dumps({"scripts":{"test":"vitest"}}),"run.py":"x",
             "CLAUDE.md":"Entry `run.py`. Test with `npm run test`.\n"})
    out=format_review(d, review(d))
    assert "tells its agent the truth" in out

def test_no_instruction_file_says_so():
    d=_repo({"main.py":"x"})
    assert "No instruction file to review" in format_review(d, review(d))

if __name__=="__main__":
    import sys as s
    fns=[v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]; bad=0
    for fn in fns:
        try: fn(); print("PASS",fn.__name__)
        except AssertionError as e: bad+=1; print("FAIL",fn.__name__,e)
    print(f"{len(fns)-bad}/{len(fns)}"); s.exit(1 if bad else 0)
