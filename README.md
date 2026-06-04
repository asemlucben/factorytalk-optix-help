# FactoryTalk Optix Help Version Browser

> **Disclaimer:** This is **not an official solution** and is **not endorsed by or affiliated with Rockwell Automation**. Use at your own discretion.

A simple static website that lets you browse all available versions of the FactoryTalk Optix online help in one place. Select a version from a dropdown and view the documentation in an embedded frame.

## Features

- **Version Selector** — Browse all discovered Optix help versions from a single dropdown  
- **Embedded Viewer** — View documentation in an iframe without leaving the site  
- **Deep Linking** — URLs are bookmarkable: `?v=1.7.3.39` to link directly to a specific version
- **SEO Friendly** — Dynamically updated meta tags, sitemap, robots.txt for search engine indexing  
- **Zero Server Setup** — Static HTML/JS hosted on GitHub Pages  
- **New Tab Links** — All help page links open in new tabs (avoids cross-origin navigation issues)

## How It Works

1. **Version Discovery** — A GitHub Actions workflow (`scan-versions.yml`) periodically scans Rockwell's cloud help server to discover the highest build for each release family and stores it in `data/versions.json`.

2. **Static Site** — The site runs on GitHub Pages (no server required). JavaScript loads the version list and manages the UI.

3. **Base Tag Injection** — A `<base>` tag is injected into the fetched HTML to ensure relative URLs (stylesheets, images, scripts) resolve against Rockwell's servers, not the GitHub Pages domain.

## Usage

1. Visit the deployed site (e.g., `https://asemlucben.github.io/factorytalk-optix-help/`)
2. Select a version from the **Version** dropdown (or "Current" for the latest 4-part build)
3. The help documentation loads in the iframe below
4. Click any link in the help → opens in a new tab
5. Share a link like `?v=1.7.3.39` to bookmark a specific version

## Limitations & Known Issues

1. **Link Navigation**: All help links open in new tabs. You cannot navigate within the iframe itself (the `<base target="_blank">` enforces this to avoid CORS errors).

2. **Search/Filters**: The help's internal search may not work reliably through the iframe. Users can use the browser's Find (Ctrl+F) instead.

3. **Third-Party Content**: Some embedded widgets, analytics, or external resources may not load if they have their own CSP policies.

4. **No Version Mirroring**: Help content is fetched on-demand. If Rockwell removes a version, it will no longer be accessible.

## Troubleshooting

### "The help content could not be embedded..."

This error can occur when:
- You are viewing from a domain that Rockwell Automation has not allowed in their CORS policy
- Rockwell's servers are temporarily unavailable
- A network issue prevents the frame from loading

Try:
- Using the "Open in new tab" button to access the help directly
- Selecting a different version
- Checking your network connection
- Verifying you're viewing from the correct GitHub Pages domain

### Links don't navigate

This is intentional — all links open in new tabs to avoid CORS issues. Close the new tab to return to the version browser.

### Version list is out of date

Run the **Scan Versions** workflow manually:
- Go to **Actions → Scan Versions → Run workflow**

It will discover any new versions and commit them.

## Disclaimer

This project is provided **as-is** for convenience and learning purposes. It is **not endorsed by or affiliated with Rockwell Automation**. Users are responsible for ensuring their use complies with Rockwell's terms of service and internal policies.
