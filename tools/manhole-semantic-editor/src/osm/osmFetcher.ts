export type OsmPoiType = 'rest_area' | 'station' | 'museum' | 'park' | 'michineki'

export type OsmPoi = {
  osmId: string
  name: string
  lat: number
  lng: number
  type: OsmPoiType
  distanceM: number
}

const ENDPOINTS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.private.coffee/api/interpreter',
]

function haversineM(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6_371_000
  const p1 = (lat1 * Math.PI) / 180
  const p2 = (lat2 * Math.PI) / 180
  const dp = ((lat2 - lat1) * Math.PI) / 180
  const dl = ((lng2 - lng1) * Math.PI) / 180
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return R * 2 * Math.asin(Math.sqrt(a))
}

export type PoiFetchConfig = { type: OsmPoiType; radiusM?: number }

function typeFromTags(tags: Record<string, string>): OsmPoiType | null {
  if (tags.highway === 'rest_area') return 'rest_area'
  if (tags.railway === 'station' || tags.railway === 'stop') return 'station'
  if (tags.tourism === 'museum' || tags.amenity === 'museum') return 'museum'
  if (tags.leisure === 'park') return 'park'
  return null
}

function buildBatchQuery(configs: PoiFetchConfig[], lat: number, lng: number): string {
  const lines: string[] = []
  for (const cfg of configs) {
    const r = cfg.radiusM ?? 2000
    const a = `(around:${r},${lat},${lng})`
    switch (cfg.type) {
      case 'rest_area':
        lines.push(`node["highway"="rest_area"]${a};`, `way["highway"="rest_area"]${a};`)
        break
      case 'station':
        lines.push(`node["railway"="station"]${a};`)
        break
      case 'museum':
        lines.push(`node["tourism"="museum"]${a};`, `way["tourism"="museum"]${a};`, `node["amenity"="museum"]${a};`, `way["amenity"="museum"]${a};`)
        break
      case 'park':
        lines.push(`way["leisure"="park"]["name"]${a};`, `relation["leisure"="park"]["name"]${a};`)
        break
    }
  }
  return `[out:json][timeout:30];\n(\n${lines.join('\n')}\n);\nout center;`
}

function parseElements(
  data: { elements?: Record<string, unknown>[] },
  lat: number,
  lng: number,
): OsmPoi[] {
  return (data.elements ?? [])
    .filter((el) => {
      const tags = el.tags as Record<string, string> | undefined
      return tags?.name && typeFromTags(tags)
    })
    .map((el) => {
      const tags = el.tags as Record<string, string>
      const elLat = (el.lat ?? (el.center as Record<string, number> | undefined)?.lat) as number
      const elLng = (el.lon ?? (el.center as Record<string, number> | undefined)?.lon) as number
      return { osmId: String(el.id), name: tags.name, lat: elLat, lng: elLng, type: typeFromTags(tags)!, distanceM: 0 }
    })
    .filter((p) => p.lat != null && p.lng != null)
    .map((p) => ({ ...p, distanceM: Math.round(haversineM(lat, lng, p.lat, p.lng)) }))
    .sort((a, b) => a.distanceM - b.distanceM)
}

const RATE_LIMIT_MSG = 'Overpass APIのレート制限に達しました。しばらく待ってから再試行してください'
const cache = new Map<string, OsmPoi[]>()

type MichinekiStation = { id: string; name: string; lat: number; lng: number }
let michinekiStations: MichinekiStation[] | null = null
const michinekiCache = new Map<string, OsmPoi[]>()

async function loadMichinekiStations(): Promise<MichinekiStation[]> {
  if (michinekiStations) return michinekiStations
  const resp = await fetch('/__editor/data/michineki')
  if (!resp.ok) throw new Error(`道の駅データの読み込みに失敗しました: ${resp.status}`)
  michinekiStations = await resp.json() as MichinekiStation[]
  return michinekiStations
}

async function queryOverpass(query: string): Promise<{ elements?: Record<string, unknown>[] }> {
  const body = `data=${encodeURIComponent(query)}`
  let lastErr: Error = new Error('No endpoint available')
  for (const endpoint of ENDPOINTS) {
    try {
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      })
      if (resp.status === 429) { lastErr = new Error(RATE_LIMIT_MSG); continue }
      if (!resp.ok) throw new Error(`Overpass API error: ${resp.status}`)
      const text = await resp.text()
      if (text.includes('rate_limited') || text.includes('runtime error')) { lastErr = new Error(RATE_LIMIT_MSG); continue }
      return JSON.parse(text)
    } catch (e) {
      if (e instanceof Error && e.message === RATE_LIMIT_MSG) { lastErr = e; continue }
      throw e
    }
  }
  throw lastErr
}

export async function fetchNearbyPoisBatch(
  configs: PoiFetchConfig[],
  lat: number,
  lng: number,
): Promise<OsmPoi[]> {
  const osmConfigs = configs.filter(c => c.type !== 'michineki')
  const michinekiConfig = configs.find(c => c.type === 'michineki')

  const results: OsmPoi[] = []

  if (osmConfigs.length > 0) {
    const cacheKey = `${lat.toFixed(4)}:${lng.toFixed(4)}:${osmConfigs.map(c => `${c.type}@${c.radiusM ?? 2000}`).join(',')}`
    if (cache.has(cacheKey)) {
      results.push(...cache.get(cacheKey)!)
    } else {
      const data = await queryOverpass(buildBatchQuery(osmConfigs, lat, lng))
      const pois = parseElements(data, lat, lng)
      cache.set(cacheKey, pois)
      results.push(...pois)
    }
  }

  if (michinekiConfig) {
    const r = michinekiConfig.radiusM ?? 2000
    const mCacheKey = `michineki:${lat.toFixed(4)}:${lng.toFixed(4)}:${r}`
    if (michinekiCache.has(mCacheKey)) {
      results.push(...michinekiCache.get(mCacheKey)!)
    } else {
      const stations = await loadMichinekiStations()
      const pois: OsmPoi[] = stations
        .map(s => ({ ...s, distanceM: Math.round(haversineM(lat, lng, s.lat, s.lng)) }))
        .filter(s => s.distanceM <= r)
        .map(s => ({ osmId: s.id, name: s.name, lat: s.lat, lng: s.lng, type: 'michineki' as OsmPoiType, distanceM: s.distanceM }))
        .sort((a, b) => a.distanceM - b.distanceM)
      michinekiCache.set(mCacheKey, pois)
      results.push(...pois)
    }
  }

  return results.sort((a, b) => a.distanceM - b.distanceM)
}
