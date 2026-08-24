"""Airflow Dataset helpers for published Bilibili videos."""

from __future__ import annotations

import re

from airflow.datasets import Dataset


_BVID_PATTERN = re.compile(r"^BV[0-9A-Za-z]{10}$")


def bilibili_video_dataset(bvid: str) -> Dataset:
    """Return a credential-free Dataset URI for a published Bilibili video."""
    if not isinstance(bvid, str) or not _BVID_PATTERN.fullmatch(bvid):
        raise ValueError("bvid must be a canonical Bilibili BV identifier")
    return Dataset(f"bilibili://video/{bvid}")
