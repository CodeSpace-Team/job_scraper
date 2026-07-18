import re

def clean_text(text, max_len=None):
    """Clean and normalize text."""
    if not text:
        return ""
    text = str(text).strip()
    text = re.sub(r'\s+', ' ', text)
    if max_len and len(text) > max_len:
        text = text[:max_len].strip()
    return text