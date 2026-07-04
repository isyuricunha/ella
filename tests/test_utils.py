"""Tests for utils module."""
from src.utils import truncate_words, count_vowels


def test_truncate_words_no_truncation():
    assert truncate_words("hello world", 5) == "hello world"


def test_truncate_words_exact():
    assert truncate_words("one two three", 3) == "one two three"


def test_truncate_words_truncates():
    result = truncate_words("one two three four five", 3)
    assert result.endswith("...")
    assert len(result.split()) <= 3


def test_count_vowels():
    assert count_vowels("hello") == 2
    assert count_vowels("sky") == 0
    assert count_vowels("AEIOU") == 5
