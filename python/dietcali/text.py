"""Tokenization shared by BM25, the head-word rule and evaluation."""
import re

STOPWORDS = {"and", "or", "with", "without", "in", "of", "to", "a", "the", "ns", "nfs", "as", "from", "made"}


def lemma(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"                       # berries -> berry
    if len(tok) > 3 and tok.endswith("es") and tok[-3] in "sxz":
        return tok[:-2]                             # boxes -> box
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]                             # beans -> bean
    return tok


def tokenize(text: str) -> list:
    toks = re.findall(r"[a-z0-9]+", str(text).lower())
    return [lemma(t) for t in toks if t not in STOPWORDS]


def head_word(term: str):
    """last content word of a search term (core food noun by convention)"""
    toks = tokenize(term)
    return toks[-1] if toks else None
