from textkit.slug import slugify


def test_repeated_separators_collapse():
    assert slugify("a  --  b") == "a-b"


def test_mixed():
    assert slugify("  Déjà Vu, again! ") in ("d-j-vu-again", "deja-vu-again", "dj-vu-again")
