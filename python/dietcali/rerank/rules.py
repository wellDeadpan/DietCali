from ..text import head_word, tokenize


def parse_exclude(exclude: str) -> list:
    """';'-separated exclude words -> lower-case list"""
    return [w.strip().lower() for w in str(exclude or "").split(";") if w.strip()]


def excluded(description: str, exclude_words: list) -> bool:
    d = description.lower()
    return any(w in d for w in exclude_words)


def head_ok(query: str, description: str) -> bool:
    """the query's head word (last content word) appears in the description"""
    h = head_word(query)
    return h is not None and h in set(tokenize(description))
