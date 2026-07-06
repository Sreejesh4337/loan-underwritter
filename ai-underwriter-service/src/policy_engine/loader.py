"""Loads and caches lending_policy.yaml.

The policy lives in its own file (per the project brief): changing a
threshold means editing the YAML, never src/policy_engine/engine.py or a
prompt. Cached per-path so a single process (or a batch eval run) only pays
the disk read once.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent.parent / "policy" / "lending_policy.yaml"


@lru_cache(maxsize=8)
def load_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f)


def policy_file_hash(path: Path = DEFAULT_POLICY_PATH) -> str:
    """Content hash of the policy file, used as part of the decide-node cache
    key so a policy edit invalidates any cached decision built against the
    old thresholds."""
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
