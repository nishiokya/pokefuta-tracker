import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { execFile } from 'node:child_process'
import type { IncomingMessage, ServerResponse } from 'node:http'

const REPO_ROOT = path.resolve(__dirname, '../..')
const NDJSON_PATH = path.join(REPO_ROOT, 'docs/pokefuta.ndjson')
const TITLES_PATH = path.join(REPO_ROOT, 'dataset/manhole_titles.json')
const MICHINEKI_PATH = path.join(REPO_ROOT, 'dataset/michineki.json')
const MANHOLEMAP_PATH = path.join(REPO_ROOT, 'dataset/manholemap.json')
const GMANHOLE_PATH = path.join(REPO_ROOT, 'docs/gmanhole.ndjson')
const WORKSPACE_DIR = path.join(__dirname, 'workspace')
const PATCHES_PATH = path.join(WORKSPACE_DIR, 'changes.ndjson')
const SCRIPTS_DIR = path.join(__dirname, 'scripts')

function jsonRes(res: ServerResponse, data: unknown, status = 200): void {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' })
  res.end(JSON.stringify(data))
}

async function handleEditorRequest(
  method: string,
  subpath: string,
  body: string,
  res: ServerResponse,
  query: string = ''
): Promise<void> {
  if (method === 'GET' && subpath === '/data/ndjson') {
    const raw = fs.readFileSync(NDJSON_PATH, 'utf-8')
    const records = raw.trim().split('\n').filter(Boolean).map(l => JSON.parse(l))
    jsonRes(res, records)
    return
  }

  if (method === 'GET' && subpath === '/data/yahoo-local') {
    const params = new URLSearchParams(query)
    const lat = params.get('lat')
    const lon = params.get('lon')
    if (!lat || !lon) { jsonRes(res, { error: 'lat/lon required' }, 400); return }
    const yahooUrl = `https://map.yahooapis.jp/search/local/V1/localSearch?appid=nishioka&lat=${lat}&lon=${lon}&dist=0.1&sort=review&output=json`
    const r = await fetch(yahooUrl)
    const text = await r.text()
    res.writeHead(r.status, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(text)
    return
  }

  if (method === 'GET' && subpath === '/data/michineki') {
    const raw = fs.readFileSync(MICHINEKI_PATH, 'utf-8')
    const jsonld = JSON.parse(raw) as { '@graph': Array<{ identifier: string; name: string; geo: { latitude: number; longitude: number } }> }
    const stations = (jsonld['@graph'] ?? []).map(s => ({
      id: s.identifier,
      name: s.name,
      lat: s.geo.latitude,
      lng: s.geo.longitude,
    }))
    jsonRes(res, stations)
    return
  }

  if (method === 'GET' && subpath === '/data/manholemap') {
    if (!fs.existsSync(MANHOLEMAP_PATH)) {
      jsonRes(res, { error: 'dataset/manholemap.json not found' }, 404)
      return
    }
    const raw = fs.readFileSync(MANHOLEMAP_PATH, 'utf-8')
    const jsonld = JSON.parse(raw) as {
      '@graph': Array<{
        identifier: string
        name?: string
        description?: string
        url: string
        image?: { contentUrl?: string }
        address?: {
          streetAddress?: string
          addressRegion?: string
          addressLocality?: string
        }
        geo?: { latitude?: number; longitude?: number }
        author?: { name?: string }
        dateCreated?: string
        interactionStatistic?: { userInteractionCount?: number }
        additionalProperty?: Array<{ name?: string; value?: string }>
      }>
    }
    const records = (jsonld['@graph'] ?? [])
      .filter(item => Number.isFinite(item.geo?.latitude) && Number.isFinite(item.geo?.longitude))
      .map(item => ({
        id: item.identifier,
        name: item.name ?? '',
        description: item.description ?? '',
        tag: item.additionalProperty?.find(prop => prop.name === 'tag')?.value ?? '',
        address: item.address?.streetAddress ?? '',
        prefecture: item.address?.addressRegion ?? '',
        municipality: item.address?.addressLocality ?? '',
        lat: item.geo!.latitude,
        lng: item.geo!.longitude,
        url: item.url,
        imageUrl: item.image?.contentUrl ?? '',
        author: item.author?.name ?? '',
        created: item.dateCreated ?? '',
        nice: item.interactionStatistic?.userInteractionCount ?? 0,
      }))
    jsonRes(res, records)
    return
  }

  if (method === 'GET' && subpath === '/data/gmanhole') {
    const raw = fs.readFileSync(GMANHOLE_PATH, 'utf-8')
    const records = raw.trim().split('\n').filter(Boolean).map(line => JSON.parse(line)) as Array<{
      id: string
      title?: string
      address?: string
      lat?: number | null
      lng?: number | null
      detail_url?: string
      status?: string
    }>
    jsonRes(res, records
      .filter(record => record.status === 'active' && Number.isFinite(record.lat) && Number.isFinite(record.lng))
      .map(record => ({
        id: record.id,
        name: record.title ?? '',
        address: record.address ?? '',
        lat: record.lat,
        lng: record.lng,
        url: record.detail_url ?? '',
      })))
    return
  }

  if (method === 'GET' && subpath === '/data/titles') {
    const raw = fs.readFileSync(TITLES_PATH, 'utf-8')
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(raw)
    return
  }

  if (method === 'POST' && subpath === '/data/titles') {
    JSON.parse(body) // validate JSON before writing
    const tmp = TITLES_PATH + '.tmp'
    fs.writeFileSync(tmp, body, 'utf-8')
    fs.renameSync(tmp, TITLES_PATH)
    jsonRes(res, { ok: true })
    return
  }

  if (method === 'GET' && subpath === '/workspace/patches') {
    if (!fs.existsSync(PATCHES_PATH)) {
      jsonRes(res, [])
      return
    }
    const raw = fs.readFileSync(PATCHES_PATH, 'utf-8')
    const patches = raw.trim().split('\n').filter(Boolean).map(l => JSON.parse(l))
    jsonRes(res, patches)
    return
  }

  if (method === 'POST' && subpath === '/workspace/patches') {
    const patch = JSON.parse(body)
    if (!fs.existsSync(WORKSPACE_DIR)) fs.mkdirSync(WORKSPACE_DIR, { recursive: true })
    fs.appendFileSync(PATCHES_PATH, JSON.stringify(patch) + '\n', 'utf-8')
    jsonRes(res, { ok: true })
    return
  }

  if (method === 'DELETE' && subpath === '/workspace/patches') {
    if (fs.existsSync(PATCHES_PATH)) fs.writeFileSync(PATCHES_PATH, '', 'utf-8')
    jsonRes(res, { ok: true })
    return
  }

  if (method === 'POST' && subpath === '/pr/create') {
    const scriptPath = path.join(SCRIPTS_DIR, 'create-pr.js')
    await new Promise<void>((resolve) => {
      execFile('node', [scriptPath], { cwd: REPO_ROOT }, (err, stdout, stderr) => {
        if (err) {
          jsonRes(res, { ok: false, error: err.message, stdout, stderr }, 500)
        } else {
          jsonRes(res, { ok: true, stdout, stderr })
        }
        resolve()
      })
    })
    return
  }

  jsonRes(res, { error: 'Not found' }, 404)
}

function editorApiPlugin(): Plugin {
  return {
    name: 'manhole-editor-api',
    configureServer(server) {
      server.middlewares.use('/__editor', (req: IncomingMessage, res: ServerResponse) => {
        const [subpath, qs] = (req.url ?? '/').split('?')
        const method = req.method ?? 'GET'
        let body = ''
        req.on('data', (chunk: Buffer) => { body += chunk.toString() })
        req.on('end', () => {
          handleEditorRequest(method, subpath, body, res, qs ?? '').catch(err => {
            res.writeHead(500, { 'Content-Type': 'application/json' })
            res.end(JSON.stringify({ error: String(err) }))
          })
        })
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), editorApiPlugin()],
  server: {
    port: 5177,
    strictPort: true,
  },
})
