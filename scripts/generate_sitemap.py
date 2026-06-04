#!/usr/bin/env python3
"""
generate_sitemap.py
-------------------
Generates sitemap.xml from data/versions.json.
Called by the deploy workflow with --base-url set to the GitHub Pages origin.
"""

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "versions.json"


def build_sitemap(base_url: str, versions: list[str], last_updated: str) -> ET.ElementTree:
    # Use the last_updated date from versions.json when available, else today
    try:
        lastmod = datetime.fromisoformat(last_updated.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        lastmod = date.today().isoformat()

    ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
    urlset = ET.Element("urlset")
    urlset.set("xmlns", ns)

    def add_url(loc: str, priority: str, changefreq: str, mod: str = lastmod) -> None:
        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = loc
        ET.SubElement(url_el, "lastmod").text = mod
        ET.SubElement(url_el, "changefreq").text = changefreq
        ET.SubElement(url_el, "priority").text = priority

    # Root — canonical homepage, loads latest version
    add_url(f"{base_url}/", "1.0", "weekly")

    # "current" alias
    add_url(f"{base_url}/?v=current", "0.9", "weekly")

    # Per-version URLs (most recent version gets highest priority)
    for idx, version in enumerate(reversed(versions)):
        priority = f"{max(0.5, 0.8 - idx * 0.05):.1f}"
        add_url(f"{base_url}/?v={version}", priority, "monthly")

    return ET.ElementTree(urlset)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sitemap.xml for the help browser.")
    parser.add_argument(
        "--base-url",
        required=True,
        help="Absolute base URL of the GitHub Pages site (no trailing slash).",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "sitemap.xml"),
        help="Output path for sitemap.xml.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    output_path = Path(args.output)

    with DATA_FILE.open() as fh:
        data = json.load(fh)

    versions: list[str] = data.get("versions", [])
    last_updated: str = data.get("last_updated", "")

    tree = build_sitemap(base_url, versions, last_updated)

    ET.indent(tree, space="  ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(fh, encoding="utf-8", xml_declaration=False)

    print(f"sitemap.xml written to {output_path} ({len(versions) + 2} URLs)")


if __name__ == "__main__":
    main()
