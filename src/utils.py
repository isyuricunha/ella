"""Utility functions for string processing."""


def truncate_words(text: str, max_words: int) -> str:
    """Truncate text to at most max_words words, appending ... if truncated."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


def count_vowels(text: str) -> int:
    """Count vowels in text."""
    return sum(1 for c in text.lower() if c in "aeiou")
