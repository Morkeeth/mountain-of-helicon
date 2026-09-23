from textkit.slug import slugify


def test_simple_word():
    assert slugify("Hello") == "hello"
