#!/usr/bin/env python3
"""
scan_versions.py
----------------
Discovers all available FactoryTalk Optix online help versions by probing
the Rockwell Automation cloud help URL pattern and updates
data/versions.json in-place (never removes existing versions).

Algorithm
---------
Starting at MAJOR.START_MINOR.0.0:
    for minor = START_MINOR, START_MINOR+1, ...:
        for patch = 0, 1, 2, ...:
            for build = 0, 1, 2, ...:
                if HEAD request → 200:  record version, try next build
                else (404):
                    if build == 0:
                        if patch == 0: STOP (this minor.0.0 missing → no further minors exist)
                        else:          break inner loop (try next patch)
                    else:
                        break inner loop (try next patch)

This captures the highest build number for each release family, e.g.
1.7.3.39 is recorded when 1.7.3.40 no longer exists.
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
MAX_PATCH = 99           # safety cap per minor release family
MAX_BUILD = 99           # safety cap per release build number

HELP_URL_TEMPLATE = (
    "https://help.optix.cloud.rockwellautomation.com"
    "/{major}.{minor}.{patch}.{build}/en/index.html"
)

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "versions.json"

REQUEST_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_url(major: int, minor: int, patch: int, build: int) -> str:
    return HELP_URL_TEMPLATE.format(
        major=major,
        minor=minor,
        patch=patch,
        build=build,
    )


def version_exists(major: int, minor: int, patch: int, build: int) -> bool:
    """Return True if the help page for this version responds with HTTP 200."""
    url = build_url(major, minor, patch, build)
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
    """Return a list of discovered version strings (e.g. ['1.7.3.39', ...])."""
    found: list[str] = []

    for minor in range(START_MINOR, MAX_MINOR + 1):
        for patch in range(0, MAX_PATCH + 1):
            latest_for_release: str | None = None

            for build in range(0, MAX_BUILD + 1):
                ver_str = f"{MAJOR}.{minor}.{patch}.{build}"
                print(f"  Checking {ver_str} … ", end="", flush=True)

                if version_exists(MAJOR, minor, patch, build):
                    print("✓ found")
                    latest_for_release = ver_str
                else:
                    print("✗ not found")
                    if build == 0:
                        if patch == 0:
                            # x.minor.0.0 not found → no further minors exist
                            print(f"\n  {MAJOR}.{minor}.0.0 not found — stopping scan.")
                            return found
                        # patch build 0 missing → try the next patch family
                        break
                    # build > 0 not found → this release family is complete
                    break

            if latest_for_release:
                found.append(latest_for_release)

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

    existing_versions: set[str] = {
        version for version in existing.get("versions", []) if len(version.split(".")) == 4
    }

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
