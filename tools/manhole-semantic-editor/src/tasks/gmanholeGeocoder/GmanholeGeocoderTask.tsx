import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

type Coordinate = { lat: number; lng: number }

type GeocodeAttempt = {
  provider: string
  strategy: string
  query: string
  result_count: number
  error: string | null
}

type GeocodeCandidate = Coordinate & {
  provider: string
  strategy: string
  query: string
  rank: number
  label: string
  score: number
  reason: string
  category?: string
  type?: string
}

type GeocodeAuditRecord = {
  id: string
  title: string
  prefecture?: string
  city?: string
  status: 'selected' | 'unresolved' | 'invalid_source_page'
  address: string
  detail_url?: string
  old_coordinate: Coordinate | null
  selected: GeocodeCandidate | null
  selection_reason: string
  old_distance_km?: number | null
  attempts: GeocodeAttempt[]
  candidates: GeocodeCandidate[]
}

type GeocodeAudit = {
  generated_at: string
  records: GeocodeAuditRecord[]
}

function markerIcon(label: string, color: string, size = 24) {
  return L.divIcon({
    className: '',
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 1px 5px rgba(0,0,0,.55);color:white;font:bold 11px/${size - 4}px system-ui;text-align:center">${label}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

function statusLabel(status: GeocodeAuditRecord['status']) {
  if (status === 'selected') return '採用済み'
  if (status === 'unresolved') return '未解決'
  return '無効ページ'
}

export function GmanholeGeocoderTask() {
  const [audit, setAudit] = useState<GeocodeAudit | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<'all' | GeocodeAuditRecord['status']>('selected')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const mapDivRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layersRef = useRef<L.Layer[]>([])

  useEffect(() => {
    fetch('/__editor/data/gmanhole-geocode-audit')
      .then(async response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`)
        return response.json() as Promise<GeocodeAudit>
      })
      .then(data => {
        setAudit(data)
        setSelectedId(data.records.find(record => record.selected)?.id ?? data.records[0]?.id ?? null)
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : String(reason)))
  }, [])

  useEffect(() => {
    if (!audit || !mapDivRef.current) return
    const map = L.map(mapDivRef.current).setView([36.5, 136], 5)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
    }).addTo(map)
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [audit])

  const records = useMemo(() => {
    if (!audit) return []
    const needle = search.trim().toLowerCase()
    return audit.records.filter(record => {
      if (status !== 'all' && record.status !== status) return false
      if (!needle) return true
      return `${record.id} ${record.title} ${record.prefecture ?? ''} ${record.city ?? ''} ${record.address}`
        .toLowerCase()
        .includes(needle)
    })
  }, [audit, search, status])

  const selected = audit?.records.find(record => record.id === selectedId) ?? null

  useEffect(() => {
    const map = mapRef.current
    if (!map || !selected) return
    layersRef.current.forEach(layer => layer.remove())
    layersRef.current = []
    const points: L.LatLngExpression[] = []

    if (selected.old_coordinate) {
      const marker = L.marker(
        [selected.old_coordinate.lat, selected.old_coordinate.lng],
        { icon: markerIcon('旧', '#ef4444', 28), zIndexOffset: 200 },
      ).addTo(map).bindPopup('旧座標')
      layersRef.current.push(marker)
      points.push([selected.old_coordinate.lat, selected.old_coordinate.lng])
    }

    selected.candidates.forEach((candidate, index) => {
      const isSelected = selected.selected
        && candidate.provider === selected.selected.provider
        && candidate.strategy === selected.selected.strategy
        && candidate.rank === selected.selected.rank
        && candidate.lat === selected.selected.lat
        && candidate.lng === selected.selected.lng
      const marker = L.marker(
        [candidate.lat, candidate.lng],
        {
          icon: markerIcon(
            isSelected ? '採' : String(index + 1),
            isSelected
              ? '#16a34a'
              : candidate.provider === 'gsi'
                ? '#2563eb'
                : candidate.provider === 'yahoo'
                  ? '#f59e0b'
                  : '#7c3aed',
            isSelected ? 30 : 24,
          ),
          zIndexOffset: isSelected ? 500 : 100,
        },
      ).addTo(map).bindPopup(
        `<b>${candidate.provider} / ${candidate.strategy}</b><br>${candidate.label}<br>score=${candidate.score}`,
      )
      layersRef.current.push(marker)
      points.push([candidate.lat, candidate.lng])
    })

    if (points.length === 1) map.setView(points[0], 17)
    else if (points.length > 1) map.fitBounds(L.latLngBounds(points).pad(0.2), { maxZoom: 17 })
  }, [selected])

  if (error) return <div className="error-banner">監査データの読み込みに失敗しました: {error}</div>
  if (!audit) return <div>ジオコーダー監査データを読み込んでいます…</div>

  const selectedCount = audit.records.filter(record => record.status === 'selected').length
  const unresolvedCount = audit.records.filter(record => record.status === 'unresolved').length
  const invalidCount = audit.records.filter(record => record.status === 'invalid_source_page').length

  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>ガンダムマンホール ジオコーダー監査</h2>
      <p style={{ color: '#6b7280', marginBottom: 16 }}>
        生成: {audit.generated_at} / 採用 {selectedCount}件 / 未解決 {unresolvedCount}件 / 無効ページ {invalidCount}件
      </p>

      <div className="filter-bar">
        <input
          value={search}
          onChange={event => setSearch(event.target.value)}
          placeholder="ID / 場所 / 住所"
          style={{ width: 280 }}
        />
        <select value={status} onChange={event => setStatus(event.target.value as typeof status)}>
          <option value="all">すべて</option>
          <option value="selected">採用済み</option>
          <option value="unresolved">未解決</option>
          <option value="invalid_source_page">無効ページ</option>
        </select>
        <span style={{ color: '#6b7280' }}>{records.length}件</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 42%) 1fr', gap: 16 }}>
        <div style={{ maxHeight: 'calc(100vh - 190px)', overflow: 'auto', background: 'white', border: '1px solid #e5e7eb', borderRadius: 8 }}>
          <table className="table">
            <thead>
              <tr><th>ID</th><th>設置場所</th><th>状態</th><th>採用</th></tr>
            </thead>
            <tbody>
              {records.map(record => (
                <tr
                  key={record.id}
                  onClick={() => setSelectedId(record.id)}
                  style={{ cursor: 'pointer', background: selectedId === record.id ? '#eff6ff' : undefined }}
                >
                  <td>{record.id}</td>
                  <td>
                    <strong>{record.title}</strong>
                    <div style={{ color: '#6b7280', fontSize: 11 }}>{record.address}</div>
                  </td>
                  <td>{statusLabel(record.status)}</td>
                  <td>
                    {record.selected
                      ? <><strong>{record.selected.provider}</strong><div style={{ fontSize: 11 }}>score {record.selected.score}</div></>
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <div ref={mapDivRef} style={{ height: 360, border: '1px solid #e5e7eb', borderRadius: 8, marginBottom: 12 }} />
          {selected && (
            <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <h3>#{selected.id} {selected.title}</h3>
                  <div style={{ color: '#6b7280', marginTop: 4 }}>{selected.address}</div>
                </div>
                {selected.detail_url && <a href={selected.detail_url} target="_blank" rel="noreferrer">公式ページ</a>}
              </div>

              <div style={{ marginTop: 12, padding: 10, borderRadius: 6, background: selected.selected ? '#f0fdf4' : '#fef2f2' }}>
                <strong>{selected.selection_reason}</strong>
                {selected.selected && (
                  <div style={{ marginTop: 4 }}>
                    {selected.selected.lat.toFixed(6)}, {selected.selected.lng.toFixed(6)}
                    {' '}({selected.selected.provider} / {selected.selected.strategy} / score {selected.selected.score})
                  </div>
                )}
                {selected.old_distance_km != null && <div>旧座標から {selected.old_distance_km} km 移動</div>}
              </div>

              <h4 style={{ marginTop: 16, marginBottom: 6 }}>問い合わせ履歴</h4>
              {selected.attempts.length === 0
                ? <div style={{ color: '#6b7280' }}>問い合わせなし</div>
                : selected.attempts.map((attempt, index) => (
                  <div key={`${attempt.provider}-${attempt.strategy}-${index}`} style={{ borderTop: '1px solid #e5e7eb', padding: '7px 0' }}>
                    <strong>{attempt.provider} / {attempt.strategy}</strong>
                    <span style={{ marginLeft: 8, color: attempt.error ? '#dc2626' : '#6b7280' }}>
                      {attempt.error ? `ERROR: ${attempt.error}` : `${attempt.result_count}件`}
                    </span>
                    <div style={{ fontFamily: 'monospace', fontSize: 11, overflowWrap: 'anywhere', marginTop: 3 }}>{attempt.query}</div>
                  </div>
                ))}

              <h4 style={{ marginTop: 16, marginBottom: 6 }}>全候補 ({selected.candidates.length})</h4>
              {selected.candidates.map((candidate, index) => (
                <div key={`${candidate.provider}-${candidate.strategy}-${candidate.rank}-${index}`} style={{ borderTop: '1px solid #e5e7eb', padding: '8px 0' }}>
                  <strong>{index + 1}. {candidate.provider} / {candidate.strategy}</strong>
                  <span style={{ marginLeft: 8 }}>score {candidate.score}</span>
                  <div>{candidate.label}</div>
                  <div style={{ fontSize: 11, color: '#6b7280' }}>
                    {candidate.lat.toFixed(6)}, {candidate.lng.toFixed(6)} / {candidate.reason}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
