import re

_MARKDOWN_ESCAPES = re.compile(r'\\([-+*_`#\[\]{}()!.>|~])')
"""
A backslash markdownify puts in front of a character that means something
special in Markdown, so the character survives unescaped.

Indeed descriptions come back through python-jobspy as Markdown, converted
from the original HTML. That conversion escapes ordinary hyphens and plus
signs -- exactly the punctuation "2-4 years" and "5+ years" are read by. Left
alone, "2\\-4 years" reads as 4 instead of 2, and "5\\+ years" is not read at
all.
"""


def clean_text(text, max_len=None):
    """Clean and normalize text."""
    if not text:
        return ""
    text = str(text).strip()
    text = _MARKDOWN_ESCAPES.sub(r'\1', text)
    text = re.sub(r'\s+', ' ', text)
    if max_len and len(text) > max_len:
        text = text[:max_len].strip()
    return text