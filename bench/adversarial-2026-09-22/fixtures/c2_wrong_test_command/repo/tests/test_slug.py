from textkit.slug import slugify


def test_spaces_become_single_hyphen():
    assert slugify("Hello  World") == "hello-world"


def test_punctuation_collapses():
    assert slugify("Rock & Roll!") == "rock-roll"
