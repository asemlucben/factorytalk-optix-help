/**
 * app.js — FactoryTalk Optix Help Browser
 *
 * Responsibilities:
 *  - Load data/versions.json and populate the version dropdown
 *  - Map ?v= query parameter to the correct iFrame URL
 *  - Update browser history (pushState) when version changes
 *  - Detect iFrame embedding failures and show a fallback
 *  - Keep <title>, <meta description> and <link rel="canonical"> in sync
 */

'use strict';

const DATA_URL   = 'data/versions.json';
const HELP_CLOUD = 'https://help.optix.cloud.rockwellautomation.com/';
const LANGUAGES = ['de', 'en', 'es', 'fr', 'it', 'ja', 'ko', 'pt', 'zh'];

// Hosts explicitly allowed by Rockwell's frame-ancestors policy (relevant subset).
// If current host is not allowed, embedding is guaranteed to fail.
const FRAME_ALLOWED_HOSTS = new Set([
  'localhost',
  'rockwellautomation.github.io'
]);

// Time (ms) to wait after iframe.onload before assuming a silent block occurred.
// Some browsers fire onload immediately when the frame is blocked.
const BLOCK_DETECT_DELAY_MS = 3000;

let versionsData = null;
let blockDetectTimer = null;
let frameLoadSucceeded = false;

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

async function init() {
  try {
    const resp = await fetch(DATA_URL);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    versionsData = await resp.json();
  } catch (err) {
    console.error('Failed to load versions.json:', err);
    showFrameError(null);
    return;
  }

  buildDropdown();
  buildLanguageDropdown();
  applyUrlState();
}

// ---------------------------------------------------------------------------
// Dropdown
// ---------------------------------------------------------------------------

function buildDropdown() {
  const select = document.getElementById('version-select');
  select.innerHTML = '';

  const { versions = [], current } = versionsData;
  const currentSegmentCount = current ? current.split('.').length : null;

  // "Current" entry always at the top
  if (current) {
    const opt = document.createElement('option');
    opt.value = 'current';
    opt.textContent = `Current (${current})`;
    select.appendChild(opt);
  }

  // Versions in descending order (latest first)
  [...versions].reverse().forEach(v => {
    if (currentSegmentCount === 4 && v.split('.').length !== currentSegmentCount) {
      return;
    }
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    if (v === current && !current) opt.textContent += ' (latest)';
    select.appendChild(opt);
  });

  select.addEventListener('change', () => {
    updateNavigationState({ version: select.value });
  });
}

function buildLanguageDropdown() {
  const select = document.getElementById('language-select');
  select.innerHTML = '';

  LANGUAGES.forEach(language => {
    const opt = document.createElement('option');
    opt.value = language;
    opt.textContent = language;
    select.appendChild(opt);
  });

  select.addEventListener('change', () => {
    updateNavigationState({ language: select.value });
  });
}

// ---------------------------------------------------------------------------
// URL state
// ---------------------------------------------------------------------------

function applyUrlState() {
  const params = new URLSearchParams(window.location.search);
  const v = params.get('v') || 'current';
  const lang = normalizeLanguage(params.get('lang'));
  setDropdownValue('version-select', v);
  setDropdownValue('language-select', lang);
  loadVersion(v, lang);
}

function setDropdownValue(selectId, v) {
  const select = document.getElementById(selectId);
  // Try exact match
  for (const opt of select.options) {
    if (opt.value === v) {
      select.value = v;
      return;
    }
  }
  // Fallback to first option (current)
  if (select.options.length > 0) select.selectedIndex = 0;
}

function normalizeLanguage(language) {
  return LANGUAGES.includes(language) ? language : 'en';
}

function updateNavigationState(changes) {
  const params = new URLSearchParams(window.location.search);
  const currentVersion = document.getElementById('version-select').value;
  const currentLanguage = document.getElementById('language-select').value;

  const nextVersion = changes.version ?? currentVersion;
  const nextLanguage = normalizeLanguage(changes.language ?? currentLanguage);

  params.set('v', nextVersion);
  params.set('lang', nextLanguage);
  history.pushState({ version: nextVersion, language: nextLanguage }, '', `?${params.toString()}`);
  loadVersion(nextVersion, nextLanguage);
}

// ---------------------------------------------------------------------------
// Version resolution & iFrame loading
// ---------------------------------------------------------------------------

function resolveVersion(v) {
  if (v === 'current') return versionsData?.current ?? null;
  return v;
}

function buildHelpUrl(resolved, language) {
  return `${HELP_CLOUD}${resolved}/${language}/index.html`;
}

function canEmbedOnCurrentHost() {
  return FRAME_ALLOWED_HOSTS.has(window.location.hostname);
}

function loadVersion(v, language = 'en') {
  const resolved = resolveVersion(v);
  if (!resolved) {
    showFrameError(null);
    return;
  }

  const url = buildHelpUrl(resolved, normalizeLanguage(language));
  const frame      = document.getElementById('help-frame');
  const errorDiv   = document.getElementById('frame-error');
  const errorLink  = document.getElementById('frame-error-link');
  const extLink    = document.getElementById('external-link');
  const loadingDiv = document.getElementById('frame-loading');

  // Update external-link and error-link targets
  extLink.href      = url;
  errorLink.href    = url;

  // Reset state: show frame + loading overlay, hide error
  frame.hidden      = false;
  errorDiv.hidden   = true;
  loadingDiv.classList.remove('hidden');
  loadingDiv.removeAttribute('aria-hidden');

  // Cancel any pending block-detection timer
  clearTimeout(blockDetectTimer);

  // Deterministic fallback: this host is not in Rockwell's frame allowlist.
  if (!canEmbedOnCurrentHost()) {
    loadingDiv.classList.add('hidden');
    loadingDiv.setAttribute('aria-hidden', 'true');
    showFrameError(url, 'blocked-host');
    updateSEO(v, resolved, language);
    return;
  }

  frame.onload = () => {
    frameLoadSucceeded = true;
    clearTimeout(blockDetectTimer);
    loadingDiv.classList.add('hidden');
    loadingDiv.setAttribute('aria-hidden', 'true');
  };

  frame.onerror = () => {
    frameLoadSucceeded = false;
    clearTimeout(blockDetectTimer);
    loadingDiv.classList.add('hidden');
    loadingDiv.setAttribute('aria-hidden', 'true');
    showFrameError(url, 'frame-error');
  };

  frame.src = url;

  // Detect silent CSP blocks: if frame doesn't load real content within timeout, show error.
  // CSP blocks often trigger onload with an error page, so we check the flag in timeout.
  frameLoadSucceeded = false;
  blockDetectTimer = setTimeout(() => {
    if (!frameLoadSucceeded) {
      loadingDiv.classList.add('hidden');
      loadingDiv.setAttribute('aria-hidden', 'true');
      showFrameError(url, 'frame-error');
    }
  }, BLOCK_DETECT_DELAY_MS);

  // Update SEO elements
  updateSEO(v, resolved, language);
}

// ---------------------------------------------------------------------------
// Fallback
// ---------------------------------------------------------------------------

function showFrameError(url, reason = 'generic') {
  const frame    = document.getElementById('help-frame');
  const errorDiv = document.getElementById('frame-error');
  const errorMsg = document.getElementById('frame-error-message');
  frame.hidden   = false;      // keep in DOM but hidden behind error overlay
  errorDiv.hidden = false;

  if (errorMsg) {
    errorMsg.textContent = reason === 'blocked-host'
      ? 'Embedding is blocked on this host by Rockwell Automation\'s frame security policy. Use the button below to open the selected version directly.'
      : 'The help content could not be embedded in this page due to cross-origin restrictions set by Rockwell Automation.';
  }

  if (url) {
    document.getElementById('frame-error-link').href = url;
  }
}

// ---------------------------------------------------------------------------
// SEO — keep meta tags and canonical in sync with current version
// ---------------------------------------------------------------------------

function updateSEO(v, resolved, language) {
  const displayVersion = v === 'current' ? `Current (${resolved})` : resolved;
  const displayLanguage = language ? ` (${language})` : '';

  document.title = `FactoryTalk Optix ${displayVersion}${displayLanguage} Help — Help Browser`;

  const desc = `FactoryTalk Optix ${displayVersion}${displayLanguage} online help documentation by Rockwell Automation.`;
  setMeta('name', 'description', desc);
  setMeta('property', 'og:description', desc);
  setMeta('property', 'og:title', `FactoryTalk Optix ${displayVersion}${displayLanguage} Help`);

  const pageUrl = `${window.location.origin}${window.location.pathname}?v=${encodeURIComponent(v)}&lang=${encodeURIComponent(normalizeLanguage(language))}`;
  const canonical = document.querySelector('link[rel="canonical"]');
  if (canonical) canonical.href = pageUrl;
  setMeta('property', 'og:url', pageUrl);
}

function setMeta(attrName, attrValue, content) {
  const el = document.querySelector(`meta[${attrName}="${attrValue}"]`);
  if (el) el.setAttribute('content', content);
}

// ---------------------------------------------------------------------------
// History navigation (Back / Forward buttons)
// ---------------------------------------------------------------------------

window.addEventListener('popstate', () => {
  applyUrlState();
});

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', init);
