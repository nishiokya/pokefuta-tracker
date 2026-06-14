import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { PokefutaRecord } from '../../semantic/semanticPatch'

type ManholeMapRecord = {
  id: string
  name: string
  description: string
  tag: string
  address: string
  prefecture: string
  municipality: string
  lat: number
  lng: number
  url: string
  imageUrl: string
  author: string
  created: string
  nice: number
}

type NearbyPair = {
  manhole: ManholeMapRecord
  pokefuta: PokefutaRecord
  distanceM: number
}

function haversineM(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const earthRadiusM = 6_371_000
  const p1 = (lat1 * Math.PI) / 180
  const p2 = (lat2 * Math.PI) / 180
  const dp = ((lat2 - lat1) * Math.PI) / 180
  const dl = ((lng2 - lng1) * Math.PI) / 180
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return earthRadiusM * 2 * Math.asin(Math.sqrt(a))
}

function markerIcon(color: string, square = false) {
  return L.divIcon({
    className: '',
    html: `<div style="width:14px;height:14px;border-radius:${square ? '3px' : '50%'};background:${color};border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,.5)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  })
}

function escapeHtml(value: string) {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

export function ManholeMapNearbyTask({ records }: { records: PokefutaRecord[] }) {
  const [manholes, setManholes] = useState<ManholeMapRecord[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [radiusM, setRadiusM] = useState(300)
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const mapDivRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.LayerGroup | null>(null)

  useEffect(() => {
    fetch('/__editor/data/manholemap')
      .then(async response => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({})) as { error?: string }
          throw new Error(body.error || `HTTP ${response.status}`)
        }
        return response.json() as Promise<ManholeMapRecord[]>
      })
      .then(setManholes)
      .catch(error => setLoadError(String(error)))
  }, [])

  const pairs = useMemo(() => {
    const activePokefuta = records.filter(record => record.status === 'active')
    const result: NearbyPair[] = []
    for (const manhole of manholes) {
      let nearest: NearbyPair | null = null
      for (const pokefuta of activePokefuta) {
        const distanceM = haversineM(manhole.lat, manhole.lng, pokefuta.lat, pokefuta.lng)
        if (distanceM <= radiusM && (!nearest || distanceM < nearest.distanceM)) {
          nearest = { manhole, pokefuta, distanceM }
        }
      }
      if (nearest) result.push(nearest)
    }
    return result.sort((a, b) => a.distanceM - b.distanceM)
  }, [manholes, radiusM, records])

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return pairs
    return pairs.filter(pair => [
      pair.manhole.name,
      pair.manhole.description,
      pair.manhole.tag,
      pair.manhole.address,
      pair.manhole.author,
      pair.pokefuta.title,
      pair.pokefuta.pokemons.join(' '),
    ].some(value => value.toLowerCase().includes(query)))
  }, [pairs, search])

  useEffect(() => {
    if (!mapDivRef.current) return
    const map = L.map(mapDivRef.current).setView([36.5, 136], 5)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map)
    mapRef.current = map
    layerRef.current = L.layerGroup().addTo(map)
    return () => {
      map.remove()
      mapRef.current = null
      layerRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const layer = layerRef.current
    if (!map || !layer) return
    layer.clearLayers()

    const visible = filtered.slice(0, 500)
    for (const pair of visible) {
      const selected = pair.manhole.id === selectedId
      const manholeMarker = L.marker([pair.manhole.lat, pair.manhole.lng], {
        icon: markerIcon(selected ? '#ef4444' : '#7c3aed', true),
      }).bindPopup(
        `<b>${escapeHtml(pair.manhole.name)}</b><br><small>${Math.round(pair.distanceM)}m / ${escapeHtml(pair.manhole.address)}</small>`,
      ).on('click', () => setSelectedId(pair.manhole.id))
      const pokefutaMarker = L.marker([pair.pokefuta.lat, pair.pokefuta.lng], {
        icon: markerIcon('#3b82f6'),
      }).bindPopup(`<b>${escapeHtml(pair.pokefuta.title)}</b>`)
      layer.addLayer(L.polyline(
        [[pair.manhole.lat, pair.manhole.lng], [pair.pokefuta.lat, pair.pokefuta.lng]],
        { color: selected ? '#ef4444' : '#94a3b8', weight: selected ? 3 : 1, opacity: 0.6, dashArray: '4,4' },
      ))
      layer.addLayer(manholeMarker)
      layer.addLayer(pokefutaMarker)
    }

    const selected = filtered.find(pair => pair.manhole.id === selectedId)
    if (selected) map.flyTo([selected.manhole.lat, selected.manhole.lng], 17, { duration: 0.5 })
  }, [filtered, selectedId])

  if (loadError) {
    return (
      <div className="error-banner">
        Manhole Mapデータ読み込みエラー: {loadError}<br />
        <code>python3 apps/tools/import_manholemap.py</code> を先に実行してください。
      </div>
    )
  }

  return (
    <div>
      <h2 style={{ marginBottom: 4 }}>Manhole Map × ポケふた</h2>
      <p style={{ marginTop: 0, color: '#6b7280', fontSize: 13 }}>
        Manhole Map全{manholes.length.toLocaleString()}件から、各ポケふたに近い投稿と説明を距離順で確認します。
      </p>

      <div className="filter-bar" style={{ marginBottom: 12 }}>
        <select value={radiusM} onChange={event => { setRadiusM(Number(event.target.value)); setSelectedId(null) }}>
          {[100, 300, 500, 1000, 3000].map(radius => (
            <option key={radius} value={radius}>{radius.toLocaleString()}m以内</option>
          ))}
        </select>
        <input
          value={search}
          onChange={event => { setSearch(event.target.value); setSelectedId(null) }}
          placeholder="説明・タグ・住所・ポケモン名で検索"
          style={{ width: 320 }}
        />
        <span style={{ color: '#6b7280', fontSize: 13 }}>{filtered.length.toLocaleString()}件</span>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 8, color: '#6b7280', fontSize: 12 }}>
        <span><b style={{ color: '#3b82f6' }}>●</b> ポケふた</span>
        <span><b style={{ color: '#7c3aed' }}>■</b> Manhole Map投稿</span>
        <span>地図表示は先頭500件まで</span>
      </div>
      <div ref={mapDivRef} style={{ height: 360, border: '1px solid #e5e7eb', borderRadius: 8, marginBottom: 12 }} />

      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 72 }}>距離</th>
            <th>ポケふた</th>
            <th>近くのマンホール情報</th>
            <th style={{ width: 120 }}>投稿</th>
          </tr>
        </thead>
        <tbody>
          {filtered.slice(0, 1000).map(pair => (
            <tr
              key={pair.manhole.id}
              onClick={() => setSelectedId(pair.manhole.id)}
              style={{ cursor: 'pointer', background: selectedId === pair.manhole.id ? '#eff6ff' : undefined }}
            >
              <td style={{ textAlign: 'right', fontWeight: 600 }}>{Math.round(pair.distanceM)}m</td>
              <td>
                <div style={{ fontWeight: 600 }}>{pair.pokefuta.title}</div>
                <small style={{ color: '#6b7280' }}>{pair.pokefuta.pokemons.join(', ')}</small>
              </td>
              <td>
                <div style={{ fontWeight: 600 }}>{pair.manhole.name}</div>
                {pair.manhole.description && pair.manhole.description !== pair.manhole.name && (
                  <div>{pair.manhole.description}</div>
                )}
                <small style={{ color: '#6b7280' }}>{pair.manhole.address}</small>
              </td>
              <td>
                <a href={pair.manhole.url} target="_blank" rel="noreferrer" onClick={event => event.stopPropagation()}>
                  元ページ
                </a>
                <div style={{ color: '#6b7280', fontSize: 11 }}>{pair.manhole.author}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
