#!/usr/bin/env python3
"""
scan_versions.py
----------------
Discovers all available FactoryTalk Optix online help versions by probing
the Rockwell Automation documentation URL pattern and updates
data/versions.json in-place (never removes existing versions).

Algorithm
---------
Starting at MAJOR.START_MINOR.0:
  for minor = START_MINOR, START_MINOR+1, ...:
    for patch = 0, 1, 2, ...:
      if HEAD request → 200:  record version, try next patch
      else (404):
        if patch == 0:  STOP (this minor.0 missing → no further minors exist)
        else:           break inner loop (try next minor)
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAJOR = 1
START_MINOR = 2          # 1.2.0 is the earliest known version
MAX_MINOR = 99           # safety cap
MAX_PATCH = 20           # safety cap per minor

HELP_URL_TEMPLATE = (
    "https://www.rockwellautomation.com/en-us/docs/factorytalk-optix"
    "/{major}-{minor}-{patch}/contents-ditamap.html"
)

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "versions.json"

REQUEST_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_url(major: int, minor: int, patch: int) -> str:
    return HELP_URL_TEMPLATE.format(major=major, minor=minor, patch=patch)


def version_exists(major: int, minor: int, patch: int) -> bool:
    """Return True if the help page for this version responds with HTTP 200."""
    url = build_url(major, minor, patch)
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0 (compatible; version-scanner/1.0)")
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT):
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        # Any other HTTP error (5xx, etc.) is treated as transient — skip this
        # version but do NOT stop the scan.
        print(f"  Warning: HTTP {exc.code} for {url}", file=sys.stderr)
        return False
    except Exception as exc:  # network errors, timeouts, etc.
        print(f"  Warning: {exc} for {url}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def scan_versions() -> list[str]:
    """Return a list of discovered version strings (e.g. ['1.2.0', ...])."""
    found: list[str] = []

    for minor in range(START_MINOR, MAX_MINOR + 1):
        found_patch_for_this_minor = False

        for patch in range(0, MAX_PATCH + 1):
            ver_str = f"{MAJOR}.{minor}.{patch}"
            print(f"  Checking {ver_str} … ", end="", flush=True)

            if version_exists(MAJOR, minor, patch):
                print("✓ found")
                found.append(ver_str)
                found_patch_for_this_minor = True
            else:
                print("✗ not found")
                if patch == 0:
                    # x.minor.0 not found → no further minors exist
                    print(f"\n  {MAJOR}.{minor}.0 not found — stopping scan.")
                    return found
                # patch > 0 not found → done with this minor, try next minor
                break

    return found


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("Loading existing versions.json …")
    existing: dict = {"versions": [], "current": None}
    if DATA_FILE.exists():
        with DATA_FILE.open() as fh:
            existing = json.load(fh)

    existing_versions: set[str] = set(existing.get("versions", []))

    print("\nScanning for versions …")
    newly_found = scan_versions()
    new_set = set(newly_found)

    added = new_set - existing_versions
    if added:
        print(f"\nNew versions discovered: {sorted(added)}")
    else:
        print("\nNo new versions discovered.")

    # Merge — never remove existing versions (guards against transient 404s)
    merged: list[str] = sorted(
        existing_versions | new_set,
        key=lambda v: tuple(int(x) for x in v.split(".")),
    )

    current = merged[-1] if merged else None

    result = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "current": current,
        "versions": merged,
    }

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")

    print(f"\nTotal versions: {len(merged)}. Current: {current}")
    print(f"Written to {DATA_FILE}")


if __name__ == "__main__":
    main()
