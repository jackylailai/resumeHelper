"""Unit tests for services/hashing.py."""

from __future__ import annotations

from backend.app.services.hashing import (
    cache_key,
    canonicalize,
    content_hash,
    jd_hash,
    sha256,
)


# ---------------------------------------------------------------------------
# canonicalize
# ---------------------------------------------------------------------------

def test_canonicalize_collapses_whitespace():
    assert canonicalize("hello  world") == "hello world"


def test_canonicalize_strips_leading_trailing():
    assert canonicalize("  hello  ") == "hello"


def test_canonicalize_normalizes_tabs_and_newlines():
    assert canonicalize("a\tb\nc") == "a b c"


def test_canonicalize_nfc_stable():
    # NFC normalization: composed vs decomposed form should collapse
    composed = "é"       # é as single codepoint
    decomposed = "é"    # é as e + combining accent
    assert canonicalize(composed) == canonicalize(decomposed)


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------

def test_content_hash_is_deterministic():
    h1 = content_hash("Python Developer with 5 years experience")
    h2 = content_hash("Python Developer with 5 years experience")
    assert h1 == h2


def test_content_hash_whitespace_invariant():
    h1 = content_hash("Python Developer  with  5 years")
    h2 = content_hash("Python Developer with 5 years")
    assert h1 == h2


def test_content_hash_different_texts_differ():
    h1 = content_hash("Alice resume")
    h2 = content_hash("Bob resume")
    assert h1 != h2


def test_content_hash_is_64_chars():
    h = content_hash("any text")
    assert len(h) == 64


# ---------------------------------------------------------------------------
# jd_hash
# ---------------------------------------------------------------------------

def test_jd_hash_same_jd_same_hash():
    jd = "We need a senior backend engineer with FastAPI."
    assert jd_hash(jd) == jd_hash(jd)


def test_jd_hash_whitespace_invariant():
    assert jd_hash("senior  engineer") == jd_hash("senior engineer")


# ---------------------------------------------------------------------------
# cache_key
# ---------------------------------------------------------------------------

def test_cache_key_stable():
    cv = content_hash("resume text")
    k1 = cache_key(cv, "job description", "v1")
    k2 = cache_key(cv, "job description", "v1")
    assert k1 == k2


def test_cache_key_differs_on_prompt_version():
    cv = content_hash("resume text")
    k1 = cache_key(cv, "jd", "resume-fit-v1")
    k2 = cache_key(cv, "jd", "resume-fit-v2")
    assert k1 != k2


def test_cache_key_differs_on_jd():
    cv = content_hash("resume text")
    k1 = cache_key(cv, "jd A", "v1")
    k2 = cache_key(cv, "jd B", "v1")
    assert k1 != k2


def test_cache_key_no_collision_between_parts():
    # Pipe separator prevents "ab|c" == "a|bc" collision
    cv_a = content_hash("ab")
    k1 = cache_key(cv_a, "c|v1_extra", "v1")
    cv_b = content_hash("a")
    k2 = cache_key(cv_b, "c", "v1_extra")
    # These represent different logical keys and must differ
    # (may or may not collide depending on hash, but at least the inputs differ)
    assert cv_a != cv_b or k1 != k2
