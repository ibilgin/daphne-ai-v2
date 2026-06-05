import express from 'express'
import cors from 'cors'
import { createProxyMiddleware } from 'http-proxy-middleware'
import fetch from 'node-fetch'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const PORT = parseInt(process.env.PORT ?? '3001', 10)
const FASTAPI_URL = process.env.FASTAPI_URL ?? 'http://localhost:8000'
const NODE_ENV = process.env.NODE_ENV ?? 'development'
const FRONTEND_DIST = path.resolve(__dirname, '../../frontend/dist')

const app = express()

// ── CORS ──────────────────────────────────────────────────────────────────────
// Only allow the Vite dev server in development. In production the BFF serves
// the built frontend from the same origin so CORS is not needed.
if (NODE_ENV !== 'production') {
  app.use(cors({
    origin: 'http://localhost:5173',
    methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization'],
    credentials: true,
  }))
}

// ── Health ─────────────────────────────────────────────────────────────────────
app.get('/health', async (_req, res) => {
  let upstream = false
  try {
    const r = await fetch(`${FASTAPI_URL}/health`, { signal: AbortSignal.timeout(3000) })
    upstream = r.ok
  } catch {
    upstream = false
  }
  res.json({ status: 'ok', upstream })
})

// ── HTML export ───────────────────────────────────────────────────────────────
// This route MUST be registered before the proxy so it is not forwarded.
app.get('/api/comics/:id/export-html', async (req, res) => {
  const { id } = req.params
  try {
    const comicRes = await fetch(`${FASTAPI_URL}/api/comics/${id}`, {
      signal: AbortSignal.timeout(15000),
    })
    if (!comicRes.ok) {
      return res.status(comicRes.status).json({ error: 'Comic not found' })
    }

    const comic = await comicRes.json()
    const html = buildSelfContainedHtml(comic)

    res.setHeader('Content-Type', 'text/html; charset=utf-8')
    res.setHeader('Content-Disposition', `attachment; filename="comic-${id}.html"`)
    res.send(html)
  } catch (err) {
    console.error('[export-html]', err)
    res.status(502).json({ error: 'Failed to fetch comic from upstream' })
  }
})

// ── Proxy all other /api/* calls to FastAPI ───────────────────────────────────
const proxy = createProxyMiddleware({
  target: FASTAPI_URL,
  changeOrigin: true,
  on: {
    error: (err, _req, res) => {
      console.error('[proxy]', err.message)
      res.status(502).json({ error: 'Upstream unavailable' })
    },
  },
})

app.use('/api', proxy)

// ── Static serving in production ──────────────────────────────────────────────
if (NODE_ENV === 'production') {
  app.use(express.static(FRONTEND_DIST))
  // SPA fallback — serve index.html for all non-API routes
  app.get('*', (_req, res) => {
    res.sendFile(path.join(FRONTEND_DIST, 'index.html'))
  })
}

// ── Start ──────────────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`BFF listening on http://localhost:${PORT}`)
  console.log(`Proxying /api/* → ${FASTAPI_URL}`)
  if (NODE_ENV === 'production') {
    console.log(`Serving frontend from ${FRONTEND_DIST}`)
  }
})

// ─────────────────────────────────────────────────────────────────────────────
// HTML Export builder
// Produces a fully self-contained file with no external dependencies.
// ─────────────────────────────────────────────────────────────────────────────

function buildSelfContainedHtml(comic) {
  const pages = comic.pages ?? []

  const coverHtml = `
    <div class="cover page">
      <div class="cover-inner">
        <div class="cover-stars">&#9733;&#9733;&#9733;&#9733;&#9733;</div>
        <h1 class="cover-title">${escHtml(comic.cover_title)}</h1>
        <hr class="cover-divider" />
        <p class="cover-for">A story for</p>
        <p class="cover-child">${escHtml(comic.child_name)}</p>
        <p class="cover-date">${formatDate(comic.created_at)}</p>
      </div>
    </div>`

  const pagesHtml = pages.map((page) => {
    const panelsHtml = (page.panels ?? []).map((panel, i) => `
      <div class="panel panel-${i}">
        ${panel.image_bytes_b64
          ? `<img src="data:image/png;base64,${panel.image_bytes_b64}" alt="${escHtml(panel.caption)}" class="panel-img" />`
          : '<div class="panel-img-placeholder"></div>'}
        ${panel.dialogue ? `<div class="speech-bubble">${escHtml(panel.dialogue)}</div>` : ''}
        <div class="panel-narration">${escHtml(panel.narration)}</div>
      </div>`).join('')

    return `
      <div class="page layout-${page.layout}">
        <div class="page-num">Page ${page.page_num}</div>
        <div class="panels layout-${page.layout}">${panelsHtml}</div>
      </div>`
  }).join('')

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>${escHtml(comic.cover_title)} — Sketch to Story</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Comic Sans MS', 'Chalkboard SE', cursive, sans-serif;
    background: #f5f5f5;
    color: #1a1a1a;
  }
  .page {
    width: 840px;
    min-height: 560px;
    margin: 32px auto;
    background: #fff;
    border: 4px solid #1a1a1a;
    border-radius: 8px;
    overflow: hidden;
    page-break-after: always;
  }
  /* Cover */
  .cover {
    background: linear-gradient(135deg, #1a237e, #3949ab);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .cover-inner {
    text-align: center;
    padding: 48px;
    color: #fff;
  }
  .cover-stars { font-size: 1.6rem; color: #ffd600; letter-spacing: 8px; margin-bottom: 20px; }
  .cover-title { font-size: 2.4rem; font-weight: 700; color: #fff; margin-bottom: 16px; }
  .cover-divider { border: none; border-top: 3px solid #ffd600; width: 60%; margin: 0 auto 16px; }
  .cover-for { font-size: 0.9rem; color: rgba(255,255,255,0.7); text-transform: uppercase; letter-spacing: 2px; }
  .cover-child { font-size: 2rem; color: #ffd600; font-weight: 700; margin-top: 4px; }
  .cover-date { margin-top: 12px; font-size: 0.85rem; color: rgba(255,255,255,0.6); }
  /* Story pages */
  .page-num {
    background: #1a1a1a;
    color: #ffd600;
    font-size: 0.75rem;
    font-weight: 700;
    padding: 4px 12px;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .panels {
    display: grid;
    gap: 4px;
    padding: 4px;
    height: calc(100% - 28px);
    min-height: 520px;
  }
  .panels.layout-1 { grid-template-columns: 1fr; grid-template-rows: 1fr; }
  .panels.layout-2 { grid-template-columns: 1fr 1fr; }
  .panels.layout-3 { grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }
  .panels.layout-3 .panel-0 { grid-column: 1 / -1; }
  .panels.layout-4 { grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }
  .panel {
    position: relative;
    display: flex;
    flex-direction: column;
    border: 3px solid #1a1a1a;
    overflow: hidden;
    background: #fff;
  }
  .panel-img {
    width: 100%;
    flex: 1;
    object-fit: cover;
    display: block;
  }
  .panel-img-placeholder {
    flex: 1;
    background: #e8e8e8;
    min-height: 120px;
  }
  .speech-bubble {
    position: absolute;
    top: 8px;
    left: 8px;
    background: #fff;
    border: 2.5px solid #1a1a1a;
    border-radius: 12px;
    padding: 6px 10px;
    max-width: 65%;
    font-size: 0.72rem;
    line-height: 1.3;
    z-index: 2;
  }
  .panel-narration {
    padding: 6px 8px;
    background: #fffde7;
    border-top: 2px solid #1a1a1a;
    font-size: 0.75rem;
    line-height: 1.4;
    min-height: 36px;
  }
  @media print {
    body { background: #fff; }
    .page { margin: 0; border: none; }
  }
</style>
</head>
<body>
${coverHtml}
${pagesHtml}
<p style="text-align:center; padding:16px; font-size:0.75rem; color:#999;">
  Created with Sketch to Story &bull; ${escHtml(comic.child_name)} &bull; ${formatDate(comic.created_at)}
</p>
</body>
</html>`
}

function escHtml(str) {
  if (!str) return ''
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}
