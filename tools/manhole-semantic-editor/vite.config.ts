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
const CHARACTER_MANHOLE_PATH = path.join(REPO_ROOT, 'docs/character_manholes.ndjson')
const GMANHOLE_GEOCODE_AUDIT_PATH = path.join(REPO_ROOT, 'dataset/gmanhole_geocode_audit.json')
const GMANHOLE_OVERRIDES_PATH = path.join(REPO_ROOT, 'dataset/gmanhole_overrides.json')
const GMANHOLE_GEOCODER_PATH = path.join(REPO_ROOT, 'apps/tools/geocode_gmanhole.py')
const WORKSPACE_DIR = path.join(__dirname, 'workspace')
const PATCHES_PATH = path.join(WORKSPACE_DIR, 'changes.ndjson')
const SCRIPTS_DIR = path.join(__dirname, 'scripts')

function jsonRes(res: ServerResponse, data: unknown, status = 200): void {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' })
  res.end(JSON.stringify(data))
}

// クライアントが <a href> に使うため、http/https 以外(javascript: 等)は空にして混入を防ぐ。
function safeHttpUrl(raw: unknown): string {
  const value = typeof raw === 'string' ? raw.trim() : ''
  return /^https?:\/\//i.test(value) ? value : ''
}

function runGmanholeGeocoder(): Promise<void> {
  return new Promise((resolve, reject) => {
    execFile(
      'python3',
      [
        GMANHOLE_GEOCODER_PATH,
        '--reuse-audit',
        GMANHOLE_GEOCODE_AUDIT_PATH,
        '--skip-yahoo',
        '--skip-nominatim',
      ],
      { cwd: REPO_ROOT },
      (error, stdout, stderr) => {
        if (error) {
          reject(new Error([error.message, stdout, stderr].filter(Boolean).join('\n')))
          return
        }
        resolve()
      },
    )
  })
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

  if (method === 'GET' && subpath === '/data/character-manholes') {
    if (!fs.existsSync(CHARACTER_MANHOLE_PATH)) {
      jsonRes(res, { error: 'docs/character_manholes.ndjson not found. Run: python3 apps/scraper/collect_character_manholes.py' }, 404)
      return
    }
    const raw = fs.readFileSync(CHARACTER_MANHOLE_PATH, 'utf-8')
    const records = raw.trim().split('\n').filter(Boolean).map(line => JSON.parse(line)) as Array<{
      id: string
      work?: string
      title?: string
      character?: string
      landmark?: string
      prefecture?: string
      city?: string
      address?: string
      lat?: number | null
      lng?: number | null
      source_url?: string
      marker_label?: string
      marker_color?: string
      status?: string
    }>
    const characterOut = records
      .filter(record => record.status === 'active' && Number.isFinite(record.lat) && Number.isFinite(record.lng))
      .map(record => ({
        id: record.id,
        work: record.work ?? '',
        title: record.title ?? '',
        character: record.character ?? '',
        landmark: record.landmark ?? '',
        prefecture: record.prefecture ?? '',
        city: record.city ?? '',
        address: record.address ?? '',
        lat: record.lat,
        lng: record.lng,
        url: safeHttpUrl(record.source_url),
        markerLabel: record.marker_label ?? '',
        markerColor: record.marker_color ?? '',
      }))

    // ガンダムは独自パイプライン(docs/gmanhole.ndjson)が真実の源。複製せず動的にマージし、
    // 種別「機動戦士ガンダム」として同じ一覧に載せる。characters は多くが未設定のため
    // landmark に設置場所(title)、character は判明分のみを入れる。
    const gundamOut: typeof characterOut = []
    if (fs.existsSync(GMANHOLE_PATH)) {
      const graw = fs.readFileSync(GMANHOLE_PATH, 'utf-8')
      const grecords = graw.trim().split('\n').filter(Boolean).map(line => JSON.parse(line)) as Array<{
        id: string
        title?: string
        prefecture?: string
        city?: string
        address?: string
        characters?: string[]
        lat?: number | null
        lng?: number | null
        detail_url?: string
        status?: string
      }>
      for (const record of grecords) {
        if (record.status !== 'active' || !Number.isFinite(record.lat) || !Number.isFinite(record.lng)) continue
        gundamOut.push({
          id: `gundam-${record.id}`,
          work: '機動戦士ガンダム',
          title: record.title ?? '',
          character: Array.isArray(record.characters) ? record.characters.join('・') : '',
          landmark: record.title ?? '',
          prefecture: record.prefecture ?? '',
          city: record.city ?? '',
          address: record.address ?? '',
          lat: record.lat,
          lng: record.lng,
          url: safeHttpUrl(record.detail_url),
        })
      }
    }

    jsonRes(res, [...characterOut, ...gundamOut])
    return
  }

  if (method === 'GET' && subpath === '/data/gmanhole-geocode-audit') {
    if (!fs.existsSync(GMANHOLE_GEOCODE_AUDIT_PATH)) {
      jsonRes(res, { error: 'dataset/gmanhole_geocode_audit.json not found' }, 404)
      return
    }
    const raw = fs.readFileSync(GMANHOLE_GEOCODE_AUDIT_PATH, 'utf-8')
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(raw)
    return
  }

  if (method === 'POST' && subpath === '/data/gmanhole-override') {
    const input = JSON.parse(body) as {
      id?: unknown
      lat?: unknown
      lng?: unknown
      official_url?: unknown
      note?: unknown
    }
    const id = String(input.id ?? '')
    const lat = Number(input.lat)
    const lng = Number(input.lng)
    const officialUrl = String(input.official_url ?? '').trim()
    const note = String(input.note ?? '').trim()

    if (!/^\d+$/.test(id)) {
      jsonRes(res, { error: '有効なマンホールIDが必要です' }, 400)
      return
    }
    if (!Number.isFinite(lat) || lat < -90 || lat > 90) {
      jsonRes(res, { error: '緯度は -90〜90 の数値で入力してください' }, 400)
      return
    }
    if (!Number.isFinite(lng) || lng < -180 || lng > 180) {
      jsonRes(res, { error: '経度は -180〜180 の数値で入力してください' }, 400)
      return
    }
    if (officialUrl && !/^https?:\/\//i.test(officialUrl)) {
      jsonRes(res, { error: '公式URLは http:// または https:// で入力してください' }, 400)
      return
    }

    const audit = JSON.parse(fs.readFileSync(GMANHOLE_GEOCODE_AUDIT_PATH, 'utf-8')) as {
      records?: Array<{ id: string }>
    }
    if (!audit.records?.some(record => String(record.id) === id)) {
      jsonRes(res, { error: `ガンダムマンホール #${id} が見つかりません` }, 404)
      return
    }

    const previousRaw = fs.existsSync(GMANHOLE_OVERRIDES_PATH)
      ? fs.readFileSync(GMANHOLE_OVERRIDES_PATH, 'utf-8')
      : '{}\n'
    const overrides = JSON.parse(previousRaw) as Record<string, Record<string, unknown>>
    const previous = overrides[id] ?? {}
    const next: Record<string, unknown> = {
      ...previous,
      lat,
      lng,
      verified_at: new Date().toISOString().slice(0, 10),
    }
    delete next.source_url
    if (officialUrl) next.official_url = officialUrl
    else delete next.official_url
    if (note) next.note = note
    else delete next.note
    overrides[id] = next

    const tmp = `${GMANHOLE_OVERRIDES_PATH}.tmp`
    fs.writeFileSync(tmp, JSON.stringify(overrides, null, 2) + '\n', 'utf-8')
    fs.renameSync(tmp, GMANHOLE_OVERRIDES_PATH)
    try {
      await runGmanholeGeocoder()
    } catch (error) {
      fs.writeFileSync(GMANHOLE_OVERRIDES_PATH, previousRaw, 'utf-8')
      jsonRes(res, { error: error instanceof Error ? error.message : String(error) }, 500)
      return
    }

    const refreshedAudit = JSON.parse(fs.readFileSync(GMANHOLE_GEOCODE_AUDIT_PATH, 'utf-8'))
    const patch = {
      id: `${Date.now()}-gmanhole-${id}`,
      createdAt: new Date().toISOString(),
      taskType: 'gmanhole_geocoder',
      operation: 'set_gmanhole_override',
      target: 'gmanholes',
      manholeIds: [Number(id)],
      payload: {
        lat,
        lng,
        official_url: officialUrl,
      },
      note,
      confidence: 'verified',
    }
    if (!fs.existsSync(WORKSPACE_DIR)) fs.mkdirSync(WORKSPACE_DIR, { recursive: true })
    fs.appendFileSync(PATCHES_PATH, JSON.stringify(patch) + '\n', 'utf-8')
    jsonRes(res, { ok: true, audit: refreshedAudit, patch })
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
