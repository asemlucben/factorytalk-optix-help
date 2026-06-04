# FactoryTalk Optix Help Viewer — Project Specification

## Overview

A static website hosted on GitHub Pages that embeds Rockwell Automation's FactoryTalk Optix online help across all available versions. A GitHub Actions workflow periodically discovers new versions and stores them in the repository. The UI offers a version dropdown and an iFrame viewer with deep-linkable URLs.

---

## SEO Strategy

The site is optimised for search-engine discoverability. Every page load updates these elements via JavaScript to reflect the selected version:

| Element | Purpose |
|---------|---------|
| `<title>` | `FactoryTalk Optix {version} Help — Help Browser` |
| `<meta name="description">` | Per-version description string |
| `<link rel="canonical">` | Absolute URL of the current `?v=` page |
| `<meta property="og:*">` | Open Graph for social/preview cards |
| `<script type="application/ld+json">` | JSON-LD `WebSite` structured data |
| `<html lang="en">` | Language declaration |

### Google Site Verification

`index.html` contains a placeholder for the Google Search Console verification meta tag:

```html
<meta name="google-site-verification" content="__GOOGLE_SITE_VERIFICATION__">
```

The **deploy workflow** substitutes this placeholder with the value of the `GOOGLE_SITE_VERIFICATION` repository secret at build time. The placeholder is never replaced in `main` — only in the built artefact deployed to GitHub Pages.

---

## Sitemap

**File generated at build time:** `sitemap.xml` (not committed to `main`)

`scripts/generate_sitemap.py` is run by the deploy workflow and outputs a `sitemap.xml` containing:

- The root URL `/` (priority 1.0, changefreq weekly)
- `/?v=current` (priority 0.9, changefreq weekly)
- `/?v={version}` for every known version (priority 0.8→0.5 descending, changefreq monthly)

`robots.txt` is also generated at build time so the `Sitemap:` directive always references the correct absolute URL.

---

## URL Conventions

The upstream help follows this pattern:

```
https://www.rockwellautomation.com/en-us/docs/factorytalk-optix/{major}-{minor}-{patch}/contents-ditamap.html
https://www.rockwellautomation.com/en-us/docs/factorytalk-optix/{major}-{minor}-{patch}/contents-ditamap/{page-path}.html
```

Version segments use **dashes**, not dots (e.g. `1-7-0`). The internal app represents versions with dots (e.g. `1.7.0`) and converts for URL construction.

---

## Version Discovery

### Algorithm

Starting at `1.2.0`, the scanner walks version space using nested iteration:

```
for minor in 2, 3, 4, ...:
    for patch in 0, 1, 2, ...:
        url = build_url(major=1, minor, patch)
        if HTTP HEAD → 200:
            record version
        else (404):
            if patch == 0:
                STOP all scanning      # x.0 missing → no more minors exist
            else:
                break inner loop       # x.N missing → try next minor
```

This matches the stated rule:
- If `1.7.1` is missing → check `1.8.0`.
- If `1.8.0` is missing → stop entirely.

### Detection Method

Use an HTTP **HEAD** request against the `contents-ditamap.html` landing page for each candidate version. A `200 OK` response indicates the version exists; a `404` indicates it does not.

### Output

Discovered versions are written to `data/versions.json`:

```json
{
  "last_updated": "2026-06-04T12:00:00Z",
  "versions": [
    "1.2.0",
    "1.3.0",
    "1.4.0",
    "1.5.0",
    "1.5.1",
    "1.6.0",
    "1.7.0"
  ]
}
```

The array is **sorted ascending**. The UI will default to the last entry (latest version).

---

## GitHub Actions Workflow

**File:** `.github/workflows/scan-versions.yml`

### Triggers

| Trigger | Schedule / Condition |
|---------|----------------------|
| `schedule` | Runs every Monday at 08:00 UTC (`cron: '0 8 * * 1'`) |
| `workflow_dispatch` | Manual trigger from the Actions tab |

### Steps

1. Checkout repository.
2. Run `scripts/scan_versions.py` (Python, no external dependencies beyond `requests`).
3. Compare the new `data/versions.json` with the committed one.
4. If changed, commit and push the updated file using a `github-actions[bot]` author.
5. (Optional) Create a GitHub Release tag for any newly discovered version.

### Permissions

The workflow needs `contents: write` permission to commit the updated `versions.json`.

---

## Static Web Application

### File Structure

```
factorytalk-optix-help/
├── .github/
│   └── workflows/
│       └── scan-versions.yml
├── data/
│   └── versions.json          # committed, updated by CI
├── scripts/
│   └── scan_versions.py       # version discovery script
├── index.html                 # single-page app entry point
├── app.js                     # UI logic
├── styles.css                 # styling
└── SPEC.md
```

### UI Layout

```
┌──────────────────────────────────────────────────────┐
│  FactoryTalk Optix Help    Version: [1.7.0 ▼]  [↗]   │
├──────────────────────────────────────────────────────┤
│                                                      │
│                   <iframe>                           │
│         (Rockwell online help content)               │
│                                                      │
└──────────────────────────────────────────────────────┘
```

- **Dropdown** — populated from `data/versions.json`, sorted descending for display (latest first).
- **iFrame** — fills the remaining viewport height.
- **External link icon (↗)** — opens the currently framed URL directly in a new tab (important fallback, see Risk section below).

### "Current" Version

The dropdown always contains a **"Current"** entry at the top (rendered as `Current (1.7.0)` to make the resolved version visible). Its URL parameter value is the literal string `current`. `versions.json` stores a `current` field pointing to the latest known version; `app.js` resolves it before constructing the iFrame URL.

### URL Scheme (Deep Linking)

The page uses **query parameters** (not hash fragments) so that URLs are indexed by search engines:

```
https://<github-pages-domain>/?v=1.7.0
https://<github-pages-domain>/?v=current
```

Query parameters work naturally with static hosting — every `?v=` URL loads `index.html`, and JavaScript reads `URLSearchParams` to set the iFrame source.

#### Routing Logic (`app.js`)

1. On page load, parse `new URLSearchParams(window.location.search).get('v')`:
   - `?v=<version>` → load that version.
   - `?v=current` or missing → load the `current` version from `versions.json`.
2. When the version dropdown changes → call `history.pushState` with the new `?v=` param (no full reload) and update the iFrame.
3. `popstate` event (browser Back/Forward) → re-parse params and update the UI.

#### URL-to-iFrame Mapping

```js
function buildHelpUrl(version) {
  const ver = version.replace(/\./g, '-');   // "1.7.0" → "1-7-0"
  const base = 'https://www.rockwellautomation.com/en-us/docs/factorytalk-optix/';
  return `${base}${ver}/contents-ditamap.html`;
}
```

---

## Risk: iFrame Embedding

> **This is the highest-risk item in the project.**

If Rockwell's servers respond with `X-Frame-Options: SAMEORIGIN` or `Content-Security-Policy: frame-ancestors 'self'`, the browser will refuse to render the iFrame and the core feature will silently fail.

### Mitigation plan

| Priority | Approach | Notes |
|----------|----------|-------|
| 1 | **Test during development** — verify the iFrame actually renders before building the full UI. | Open browser DevTools → Console; a refused-frame error appears immediately. |
| 2 | **Always expose an "Open in new tab" link** — so the page is still useful even if embedding is blocked. | Already included in the layout above. |
| 3 | **Display a clear error message** in the iFrame area if the frame fails to load, with a direct link. | Use the `iframe.onerror` and a timeout-based load-check heuristic. |
| 4 | *(Fallback)* **Mirror / archive the help content** via a separate scraping workflow and serve it from the GitHub Pages origin. | This avoids the cross-origin problem entirely but requires significantly more storage and legal review. |

---

## CI / CD Pipeline

Two workflows handle the project lifecycle:

### `scan-versions.yml` — Version Discovery

| Trigger | When |
|---------|------|
| `schedule` | Every Monday 08:00 UTC |
| `workflow_dispatch` | Manual |

Steps: checkout → run `scripts/scan_versions.py` → if `data/versions.json` changed, commit and push back to `main` → this push triggers the deploy workflow.

Permissions: `contents: write`.

### `deploy.yml` — Build & Publish

| Trigger | When |
|---------|------|
| `push` to `main` | Any commit (including the scan bot commit) |
| `workflow_run` on `scan-versions` completed | Ensures deploy follows scan |
| `workflow_dispatch` | Manual |

Steps:
1. Checkout.
2. Set Python up; run `scripts/generate_sitemap.py --base-url <pages-url>`.
3. Copy source files to `dist/`.
4. `sed` substitute `__GOOGLE_SITE_VERIFICATION__` → `${{ secrets.GOOGLE_SITE_VERIFICATION }}` in `dist/index.html`.
5. `sed` substitute `__BASE_URL__` → computed GitHub Pages URL in `dist/index.html`.
6. Generate `dist/robots.txt` with the correct absolute `Sitemap:` directive.
7. Upload `dist/` as a Pages artefact and deploy via `actions/deploy-pages`.

Permissions: `contents: read`, `pages: write`, `id-token: write`.

---

## Cross-Origin Navigation Tracking

Because the iFrame content is on a different origin, `iframe.contentWindow.location` is **not readable** by script (throws `SecurityError`). To track which page the user is on inside the iFrame:

- Listen for `hashchange` or `popstate` events emitted by the iFrame's page (only works if the upstream site opts in with `postMessage`).
- As a fallback, intercept clicks on the version dropdown (which the page controls) and update the hash, but accept that sub-page navigation inside the iFrame will not be reflected in the parent URL.

The spec accepts this limitation at v1. The external link (↗) will always link to `contents-ditamap.html` for the selected version unless cross-origin navigation tracking can be confirmed to work.

---

## Data File Management

- `data/versions.json` is committed to `main` and served as a static asset by GitHub Pages.
- The scan script reads the current file first and does a **merge** (never removes versions, only adds), protecting against transient 404s caused by upstream maintenance.
- A `last_updated` timestamp is always written so the UI can display "last checked" info.

---

## Out of Scope (v1)

- Serving mirrored/cached copies of the help content.
- Full-text search across versions.
- Diff view between two versions.
- Authentication or access control.
