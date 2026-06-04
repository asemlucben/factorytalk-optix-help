#!/usr/bin/env python3
"""
scan_versions.py
----------------
Discovers all available FactoryTalk Optix online help versions by probing
the qplatform help URL pattern and updates
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

This captures the highest build number for each release family even when
build numbers are sparse (for example, a high build like 1.7.0.804).
"""

import json
import sys
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAJOR = 1
START_MINOR = 3          # 1.3.5.2 is the earliest known version we have found
MAX_MINOR = 99           # safety cap
MAX_PATCH = 99           # safety cap per minor release family
MAX_BUILD = 1200         # safety cap per release build number
MAX_BUILD_MISS_STREAK = 1000  # stop patch scan after this many misses after a hit
MAX_EMPTY_MINORS = 3     # stop after this many empty minors once discovery started
BUILD_BATCH_SIZE = 128    # number of builds to probe per concurrent batch
MAX_WORKERS = 32         # thread count for parallel HEAD probes

HELP_URL_TEMPLATE = (
    "https://ftoptix-help.qplatform.it"
    "/{major}.{minor}.{patch}.{build}/en/index.html"
)

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "versions.json"

REQUEST_TIMEOUT = 2  # seconds


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


def probe_build_batch(
    executor: ThreadPoolExecutor,
    major: int,
    minor: int,
    patch: int,
    build_start: int,
    build_end: int,
) -> list[tuple[int, bool]]:
    """Probe a contiguous build range in parallel and return ordered results."""
    futures = {
        executor.submit(version_exists, major, minor, patch, build): build
        for build in range(build_start, build_end + 1)
    }

    result_map: dict[int, bool] = {}
    for future in as_completed(futures):
        build = futures[future]
        result_map[build] = future.result()

    return [(build, result_map[build]) for build in range(build_start, build_end + 1)]


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def scan_versions() -> list[str]:
    """Return a list of discovered version strings (e.g. ['1.7.3.39', ...])."""
    found: list[str] = []
    empty_minor_streak = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for minor in range(START_MINOR, MAX_MINOR + 1):
            found_in_minor = False
            found_patch_in_minor = False

            for patch in range(0, MAX_PATCH + 1):
                latest_for_release: str | None = None
                miss_streak = 0
                build = 0
                stop_patch_scan = False

                while build <= MAX_BUILD:
                    batch_end = min(build + BUILD_BATCH_SIZE - 1, MAX_BUILD)
                    batch_results = probe_build_batch(
                        executor,
                        MAJOR,
                        minor,
                        patch,
                        build,
                        batch_end,
                    )

                    for build_number, exists in batch_results:
                        ver_str = f"{MAJOR}.{minor}.{patch}.{build_number}"
                        print(f"  Checking {ver_str} … ", end="", flush=True)

                        if exists:
                            print("✓ found")
                            latest_for_release = ver_str
                            miss_streak = 0
                        else:
                            print("✗ not found")
                            if latest_for_release is not None:
                                miss_streak += 1
                            if latest_for_release is not None and miss_streak >= MAX_BUILD_MISS_STREAK:
                                # Build numbers can be sparse; stop only after a long
                                # consecutive miss run once this patch family started.
                                stop_patch_scan = True
                                break

                    if stop_patch_scan:
                        break

                    build = batch_end + 1

                if latest_for_release:
                    found.append(latest_for_release)
                    found_in_minor = True
                    found_patch_in_minor = True
                elif patch == 0:
                    # If x.minor.0.x does not exist at all, higher patch families
                    # for the same minor are not expected.
                    break
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
