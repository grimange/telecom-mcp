"""Fault injection helpers for chaos scenarios."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator


@contextmanager
def patched_attr(obj: Any, attr: str, value: Any) -> Iterator[None]:
    original = getattr(obj, attr)
    setattr(obj, attr, value)
    try:
        yield
    finally:
        setattr(obj, attr, original)
