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
                if HEAD request → 200:  record the latest build for this release family
                else (404):
                    if we have already seen a valid build in this patch family:
                        break inner loop (this release family is complete)
                    else:
                        continue probing later build numbers

            if no build was found for this patch family:
                if we have already found at least one patch in this minor:
                    break patch loop (no need to probe higher patch numbers)
                else:
                    continue probing next patch family

The scanner does not stop on the first missing minor. Some minors have gaps
at the beginning (for example, 1.2.x.x may be absent while 1.3.x.x exists),
so the scan only stops after a small run of consecutive empty minors once at
least one version has already been discovered.

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
START_MINOR = 3          # 1.3.5.2 is the earliest known version we have found
MAX_MINOR = 99           # safety cap
MAX_PATCH = 99           # safety cap per minor release family
MAX_BUILD = 99           # safety cap per release build number
MAX_EMPTY_MINORS = 3     # stop after this many empty minors once discovery started

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
    empty_minor_streak = 0

    for minor in range(START_MINOR, MAX_MINOR + 1):
        found_in_minor = False
        found_patch_in_minor = False

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
                    if latest_for_release is not None:
                        # We have already seen this patch family; the first gap
                        # after a hit means the family has ended.
                        break
                    # Leading gaps are allowed, so keep probing later builds.

            if latest_for_release:
                found.append(latest_for_release)
                found_in_minor = True
                found_patch_in_minor = True
            elif found_patch_in_minor:
                # Once a minor has started yielding patch families, the first
                # fully missing patch family means higher patch numbers are not
                # expected for that same minor line.
                break

        if found_in_minor:
            empty_minor_streak = 0
            continue

        if found:
            empty_minor_streak += 1
            if empty_minor_streak >= MAX_EMPTY_MINORS:
                print(f"\n  No versions found for {MAX_EMPTY_MINORS} consecutive minors — stopping scan.")
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
