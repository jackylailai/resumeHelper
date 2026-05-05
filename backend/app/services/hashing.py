from __future__ import annotations

import hashlib
import re
import unicodedata


def canonicalize(text: str) -> str:
    """NFC-normalize, collapse whitespace, strip leading/trailing whitespace."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def content_hash(parsed_text: str) -> str:
    return sha256(canonicalize(parsed_text))


def jd_hash(job_description: str) -> str:
    return sha256(canonicalize(job_description))


def cache_key(cv_hash: str, jd: str, prompt_version: str) -> str:
    """Deterministic cache key for (resume content, JD, prompt version) triple."""
    return sha256(f"{cv_hash}|{jd_hash(jd)}|{prompt_version}")
