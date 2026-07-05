import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

type CharacterManhole = {
  id: string
  work: string
  title: string
  character: string
  landmark: string
  prefecture: string
  city: string
  address: string
  lat: number
  lng: number
  url: string
  markerLabel: string
  markerColor: string
}

// 種別ごとの識別色 (登場順に割り当て)
const WORK_COLORS = ['#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316']

function markerIcon(color: string) {
  return L.divIcon({
    className: '',
    html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,.5)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  })
}

function escapeHtml(value: string) {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// http/https 以外(javascript: 等)はリンク化しない。
function safeUrl(raw: string) {
  return /^https?:\/\//i.test(raw.trim()) ? raw.trim() : ''
}

export function CharacterManholesTask() {
  const [records, setRecords] = useState<CharacterManhole[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedWork, setSelectedWork] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const mapDivRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.LayerGroup | null>(null)

  useEffect(() => {
    fetch('/__editor/data/character-manholes')
      .then(async response => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({})) as { error?: string }
          throw new Error(body.error || `HTTP ${response.status}`)
        }
        return response.json() as Promise<CharacterManhole[]>
      })
      .then(setRecords)
      .catch(error => setLoadError(String(error)))
  }, [])

  // 種別(作品)ごとの件数と色
  const works = useMemo(() => {
    const counts = new Map<string, number>()
    for (const record of records) counts.set(record.work, (counts.get(record.work) ?? 0) + 1)
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([work, count], index) => {
        const markerRecord = records.find(record => record.work === work)
        return {
          work,
          count,
          color: /^#[0-9a-f]{6}$/i.test(markerRecord?.markerColor ?? '')
            ? markerRecord!.markerColor
            : WORK_COLORS[index % WORK_COLORS.length],
          label: markerRecord?.markerLabel || 'キ',
        }
      })
  }, [records])

  const colorByWork = useMemo(() => {
    const map = new Map<string, string>()
    for (const entry of works) map.set(entry.work, entry.color)
    return map
  }, [works])

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return records.filter(record => {
      if (selectedWork !== 'all' && record.work !== selectedWork) return false
      if (!query) return true
      return [record.work, record.character, record.landmark, record.city, record.address, record.title]
        .some(value => value.toLowerCase().includes(query))
    })
  }, [records, selectedWork, search])

  // 地図の初期化 (一度きり)
  useEffect(() => {
    if (!mapDivRef.current) return
    const map = L.map(mapDivRef.current).setView([33.25, 130.3], 9)
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

  // マーカー再描画 + 範囲フィット
  useEffect(() => {
    const map = mapRef.current
    const layer = layerRef.current
    if (!map || !layer) return
    layer.clearLayers()

    for (const record of filtered) {
      const selected = record.id === selectedId
      const color = colorByWork.get(record.work) ?? '#6b7280'
      const marker = L.marker([record.lat, record.lng], {
        icon: markerIcon(selected ? '#111827' : color),
        zIndexOffset: selected ? 1000 : 0,
      }).bindPopup(
        `<b>${escapeHtml(record.character)}</b><br>` +
        `<small>${escapeHtml(record.work)}</small><br>` +
        `<small>${escapeHtml(record.landmark)}</small><br>` +
        `<small>${escapeHtml(record.prefecture)}${escapeHtml(record.city)}</small>`,
      ).on('click', () => setSelectedId(record.id))
      layer.addLayer(marker)
    }

    const selectedRecord = filtered.find(record => record.id === selectedId)
    if (selectedRecord) {
      map.flyTo([selectedRecord.lat, selectedRecord.lng], 16, { duration: 0.5 })
    } else if (filtered.length > 0) {
      const bounds = L.latLngBounds(filtered.map(record => [record.lat, record.lng] as [number, number]))
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 12 })
    }
  }, [filtered, selectedId, colorByWork])

  if (loadError) {
    return (
      <div className="error-banner">
        キャラクターマンホールデータ読み込みエラー: {loadError}<br />
        <code>python3 apps/scraper/collect_character_manholes.py</code> を先に実行してください。
      </div>
    )
  }

  return (
    <div>
      <h2 style={{ marginBottom: 4 }}>キャラクターマンホール（種別ごと）</h2>
      <p style={{ marginTop: 0, color: '#6b7280', fontSize: 13 }}>
        ポケふた以外のキャラクターマンホールを作品（種別）ごとに表示します。全{records.length.toLocaleString()}件・{works.length}種別。
        <br />出典: <code>docs/character_manholes.ndjson</code>（マイマップKML/座標化）＋ <code>docs/gmanhole.ndjson</code>（ガンダム）・読み取り専用。
      </p>

      {/* 種別サマリ（クリックで絞り込み） */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
        <button
          className={`btn${selectedWork === 'all' ? ' btn-primary' : ''}`}
          onClick={() => { setSelectedWork('all'); setSelectedId(null) }}
        >
          すべて <b>{records.length}</b>
        </button>
        {works.map(entry => (
          <button
            key={entry.work}
            className={`btn${selectedWork === entry.work ? ' btn-primary' : ''}`}
            onClick={() => { setSelectedWork(entry.work); setSelectedId(null) }}
          >
            <span style={{ display: 'inline-flex', width: 18, height: 18, borderRadius: '50%', background: entry.color, color: '#fff', marginRight: 6, alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700 }}>
              {entry.label.slice(0, 1)}
            </span>
            {entry.work} <b>{entry.count}</b>
          </button>
        ))}
      </div>

      <div className="filter-bar" style={{ marginBottom: 12 }}>
        <input
          value={search}
          onChange={event => { setSearch(event.target.value); setSelectedId(null) }}
          placeholder="キャラ・設置場所・市・住所で検索"
          style={{ width: 320 }}
        />
        <span style={{ color: '#6b7280', fontSize: 13 }}>{filtered.length.toLocaleString()}件</span>
      </div>

      <div ref={mapDivRef} style={{ height: 380, border: '1px solid #e5e7eb', borderRadius: 8, marginBottom: 12 }} />

      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 150 }}>種別</th>
            <th style={{ width: 130 }}>キャラ</th>
            <th>設置場所</th>
            <th style={{ width: 110 }}>市区町村</th>
            <th>住所</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map(record => (
            <tr
              key={record.id}
              onClick={() => setSelectedId(record.id)}
              onKeyDown={event => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  setSelectedId(record.id)
                }
              }}
              role="button"
              tabIndex={0}
              aria-pressed={selectedId === record.id}
              style={{ cursor: 'pointer', background: selectedId === record.id ? '#eff6ff' : undefined }}
            >
              <td>
                <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: colorByWork.get(record.work) ?? '#6b7280', marginRight: 6 }} />
                {record.work}
              </td>
              <td style={{ fontWeight: 600 }}>{record.character}</td>
              <td>{record.landmark}</td>
              <td>{record.city}</td>
              <td>
                <small style={{ color: '#6b7280' }}>{record.address}</small>
                {safeUrl(record.url) && (
                  <>
                    {' '}
                    <a href={safeUrl(record.url)} target="_blank" rel="noreferrer" onClick={event => event.stopPropagation()}>出典</a>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
