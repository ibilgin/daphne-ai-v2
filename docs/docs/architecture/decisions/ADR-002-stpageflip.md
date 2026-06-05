# ADR-002: Use StPageFlip for Page-Turn Animation

**Status**: Accepted  
**Date**: 2026-05-02  
**Deciders**: Frontend team

---

## Context

The Vue 3 comic reader needs to present multi-page comics with a realistic page-turn effect to deliver an engaging reading experience for children and parents. The reader must:

- Display HTML-rendered comic pages (panels, images, speech bubbles) — not PDFs or canvas-only renders.
- Support navigation: next/prev, jump-to-page.
- Work without a backend connection once the comic is loaded.
- Be compatible with Vue 3's `<script setup>` and the component lifecycle (`onMounted`, `onBeforeUnmount`).

---

## Decision

We use the **`page-flip` npm package** (StPageFlip), which implements a 3D CSS/WebGL page-turn animation from DOM elements.

Integration pattern:
1. Hidden `<div>` elements are rendered in the Vue template (one per page), containing the full comic panel markup.
2. On `onMounted`, after `nextTick` to ensure the DOM is ready, `new PageFlip(containerEl, options)` is called.
3. `book.loadFromHTML(pageElements)` is called with an array of the hidden DOM refs.
4. The `PageFlip` instance is destroyed in `onBeforeUnmount` to prevent memory leaks.
5. `next()`, `prev()`, and `goTo(n)` are exposed via `defineExpose()` so the parent `ReaderView` can control navigation from the toolbar.

---

## Alternatives Considered

### Turn.js
- **Pros**: Well-known, used in many digital publications.
- **Cons**: jQuery-dependent. Incompatible with Vue 3 + Vite without significant shim work. Last maintained 2018.

### CSS 3D flip (custom)
- **Pros**: No third-party dependency; full control.
- **Cons**: Correctly implementing the page-fold physics (shadow gradient, perspective, touch events) is a multi-week effort. StPageFlip provides this out of the box.

### PDF.js reader (Mozilla)
- **Pros**: Battle-tested PDF rendering.
- **Cons**: Comic panels are HTML/CSS, not PDFs. Generating PDFs server-side adds an unnecessary rendering step and prevents client-side customisation of layout.

### Epub.js
- **Pros**: Standard ebook format support.
- **Cons**: Requires EPUB packaging of the comic. Adds a non-trivial server-side build step and adds complexity for a single-comic-type platform.

---

## Consequences

**Positive**:
- Delivers a delightful, book-like reading experience appropriate for a children's platform.
- HTML-based pages mean speech bubbles, narration text, and panel grids are rendered natively by the browser — no canvas rasterisation needed.
- Responsive: StPageFlip supports portrait (single-page) and landscape (spread) modes.

**Negative**:
- StPageFlip clones DOM nodes internally. If Vue reactive refs are inside the hidden page divs, they may stop being reactive after `loadFromHTML`. Comic page content must be treated as static after the book initialises.
- The `page-flip` package is maintained by a single author; long-term support is not guaranteed. Pinning the version in `package.json` mitigates this risk.
- `loadFromHTML` must be called after `nextTick` — calling it synchronously in `onMounted` will silently produce an empty book.
