"""
Governance Gate Runner — Sketch to Story platform, Phase 5.

Reads governance.yaml and evaluates each check.  Exits 0 if all required checks
pass, exits 1 if any required check fails.

Runnable as:
    python backend/governance/gate_runner.py

Called as a CI step in model-ci.yml BEFORE the register step.

A check is considered failed if:
  - status != "pass"   (for type: boolean)
  - status != "pass"   (for type: metric — threshold enforcement is done at
    eval time; gate_runner treats the pre-set status as the source of truth)
  - last_verified is more than 30 days ago (stale check)
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate governance.yaml relative to this file
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
_GOVERNANCE_YAML = _HERE / "governance.yaml"

# ---------------------------------------------------------------------------
# Staleness threshold
# ---------------------------------------------------------------------------
_STALE_DAYS = 30


def _load_yaml(path: Path) -> dict:
    """Load YAML, falling back to a helpful error if PyYAML is missing."""
    try:
        import yaml
    except ImportError:
        print(
            "ERROR: PyYAML is not installed. "
            "Run: uv pip install pyyaml",
            file=sys.stderr,
        )
        sys.exit(1)

    with path.open("r") as fh:
        return yaml.safe_load(fh)


def _is_stale(last_verified: str | None) -> bool:
    """Return True if last_verified is more than _STALE_DAYS ago."""
    if not last_verified:
        return True
    try:
        dt = datetime.fromisoformat(str(last_verified)).replace(tzinfo=timezone.utc)
        return datetime.now(tz=timezone.utc) - dt > timedelta(days=_STALE_DAYS)
    except ValueError:
        return True


def run_gate(governance_yaml_path: Path = _GOVERNANCE_YAML) -> int:
    """
    Evaluate all checks in governance.yaml.

    Returns
    -------
    0 — all required checks pass.
    1 — one or more required checks fail.
    """
    if not governance_yaml_path.exists():
        print(
            f"FATAL: governance.yaml not found at {governance_yaml_path}",
            file=sys.stderr,
        )
        return 1

    config = _load_yaml(governance_yaml_path)
    checks: dict = config.get("checks", {})

    if not checks:
        print("FATAL: No checks found in governance.yaml.", file=sys.stderr)
        return 1

    passed: list[str] = []
    failed: list[tuple[str, str]] = []  # (check_key, reason)
    skipped: list[str] = []

    print("=" * 60)
    print("Governance Gate Runner")
    print(f"Config: {governance_yaml_path}")
    print(f"Date  : {datetime.now(tz=timezone.utc).date().isoformat()}")
    print("=" * 60)

    for key, check in checks.items():
        required: bool = check.get("required", False)
        status: str = check.get("status", "unknown")
        name: str = check.get("name", key)
        last_verified: str | None = check.get("last_verified")

        if not required:
            skipped.append(key)
            print(f"  SKIP  [{key}] {name} (required=false)")
            continue

        reasons: list[str] = []

        # Status check
        if status != "pass":
            reasons.append(f"status='{status}' (expected 'pass')")

        # Staleness check
        if _is_stale(last_verified):
            reasons.append(
                f"last_verified='{last_verified}' is more than {_STALE_DAYS} days ago"
            )

        if reasons:
            reason_str = "; ".join(reasons)
            failed.append((key, reason_str))
            print(f"  FAIL  [{key}] {name}")
            print(f"        reason: {reason_str}")
        else:
            passed.append(key)
            print(f"  PASS  [{key}] {name}")

    print("=" * 60)
    print(f"Results: {len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped")

    if failed:
        print("\nFailed checks:")
        for key, reason in failed:
            print(f"  - {key}: {reason}")
        print("\nGovernance gate FAILED — model promotion blocked.")
        return 1

    print("\nAll required governance checks passed.")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(run_gate())
