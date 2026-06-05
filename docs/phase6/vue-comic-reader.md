Scaffold a Vue 3 + PrimeVue 4 comic book viewer for the Sketch to Story platform.

Create the full frontend project:

1. package.json — dependencies: vue@3, vue-router@4, pinia, primevue@4, @primevue/themes, primeicons, page-flip, axios. devDependencies: vite, @vitejs/plugin-vue.

2. src/main.js — create app, install PrimeVue with Aura theme preset and ripple, install Router and Pinia.

3. src/router/index.js — routes: / → LibraryView, /generate → GenerateView, /read/:comicId → ReaderView.

4. src/stores/comic.js — Pinia store. State: {library: Comic[], currentComic: Comic|null, activeJob: Job|null}. Actions: fetchLibrary(), fetchComic(id), submitDrawing(formData), pollJob(jobId) [polls every 2s, resolves when status=complete, rejects on failed].

5. src/components/ComicBook.vue — wraps StPageFlip. Props: comic (ComicSchema). onMounted: new PageFlip(containerEl, {width:420, height:560, showCover:true, flippingTime:700, usePortrait:false}), then book.loadFromHTML(pageElements). Expose: next(), prev(), goTo(n) methods. Emits: page-changed(num).

6. src/components/ComicPanel.vue — Props: panel (PanelSchema), layout-index. Renders: <img> with base64 drawing, narration text below, speech bubble (absolute positioned, top-left) if dialogue present. Speech bubble styled as classic comic callout with CSS tail.

7. src/components/CoverPage.vue — Props: comic. Full-height cover: comic title (generated from story), child name, creation date, decorative border. Uses PrimeVue Card styling.

8. src/views/ReaderView.vue — fetches comic by route param. Full-viewport layout. Toolbar (PrimeVue Toolbar): prev button, page indicator "2 / 10", next button, fullscreen toggle, back-to-library button. Main area: ComicBook component. Bottom: thumbnail strip (small page previews, clickable).

9. src/views/LibraryView.vue — PrimeVue DataView in grid layout. Each item: comic cover image, title, child name, date badge, "Read" button. Empty state with illustration and "Create your first comic" CTA.

10. src/views/GenerateView.vue — Stepper (PrimeVue Stepper): Step 1: FileUpload (drag-drop, image only, preview), child name InputText, age group Select. Step 2: style selector (6 PrimeVue ToggleButton cards with style name + description). Step 3: JobStatus component showing live progress. On complete: auto-navigate to ReaderView.

11. src/components/JobStatus.vue — Props: jobId. Polls store.pollJob. Shows: PrimeVue ProgressBar (value=progress_pct), current stage label with icon, animated status message. Error state with retry button.

Use PrimeVue Aura theme throughout. All API calls go through the Pinia store to axios base URL from VITE_API_URL env var.