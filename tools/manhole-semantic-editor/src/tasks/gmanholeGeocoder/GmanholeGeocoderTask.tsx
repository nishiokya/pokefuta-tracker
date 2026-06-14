import { useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { SemanticPatch } from '../../semantic/semanticPatch'

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
  override?: {
    status?: string
    installation_status?: string
    installed_at?: string
    verified_at?: string
    official_url?: string
    source_url?: string
    note?: string
    lat?: number
    lng?: number
  } | null
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

type SortOrder = 'suspicious' | 'score' | 'distance' | 'id'

function reviewPriority(record: GeocodeAuditRecord): { score: number; reasons: string[] } {
  if (!record.selected) {
    return {
      score: record.status === 'unresolved' ? 200 : 0,
      reasons: record.status === 'unresolved' ? ['採用候補なし'] : [],
    }
  }
  if (record.selected.provider === 'manual' && record.selected.strategy === 'verified_override') {
    return { score: -1, reasons: ['手動確認済み'] }
  }

  let score = Math.max(0, 100 - record.selected.score)
  const reasons: string[] = []
  if (record.selected.score < 80) reasons.push(`低スコア ${record.selected.score}`)

  const strategyWeights: Record<string, number> = {
    address_without_number: 30,
    title_locality: 35,
    place_name: 40,
  }
  const strategyWeight = strategyWeights[record.selected.strategy] ?? 0
  if (strategyWeight > 0) {
    score += strategyWeight
    reasons.push(`曖昧な検索 ${record.selected.strategy}`)
  }

  const distance = record.old_distance_km ?? 0
  if (distance >= 10) {
    score += 50
    reasons.push(`旧座標から ${distance.toFixed(1)}km`)
  } else if (distance >= 1) {
    score += 30
    reasons.push(`旧座標から ${distance.toFixed(1)}km`)
  } else if (distance >= 0.3) {
    score += 15
    reasons.push(`旧座標から ${distance.toFixed(1)}km`)
  }

  if (reasons.length === 0) reasons.push('目立つ警告なし')
  return { score, reasons }
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

function candidatePopup(candidate: GeocodeCandidate): HTMLElement {
  const container = document.createElement('div')
  const title = document.createElement('strong')
  title.textContent = `${candidate.provider} / ${candidate.strategy}`
  container.append(title, document.createElement('br'))
  container.append(document.createTextNode(candidate.label), document.createElement('br'))
  container.append(document.createTextNode(`score=${candidate.score}`))
  return container
}

type Props = {
  onPatchSaved?: (patch: SemanticPatch) => void
}

export function GmanholeGeocoderTask({ onPatchSaved }: Props) {
  const [audit, setAudit] = useState<GeocodeAudit | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<'all' | GeocodeAuditRecord['status']>('selected')
  const [sortOrder, setSortOrder] = useState<SortOrder>('suspicious')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [overrideLat, setOverrideLat] = useState('')
  const [overrideLng, setOverrideLng] = useState('')
  const [overrideOfficialUrl, setOverrideOfficialUrl] = useState('')
  const [overrideNote, setOverrideNote] = useState('')
  const [draftCoordinate, setDraftCoordinate] = useState<Coordinate | null>(null)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)
  const mapDivRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layersRef = useRef<L.Layer[]>([])
  const draftMarkerRef = useRef<L.Marker | null>(null)

  useEffect(() => {
    fetch('/__editor/data/gmanhole-geocode-audit')
      .then(async response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`)
        return response.json() as Promise<GeocodeAudit>
      })
      .then(data => {
        setAudit(data)
        const mostSuspicious = data.records
          .filter(record => record.status === 'selected')
          .sort((left, right) => reviewPriority(right).score - reviewPriority(left).score)[0]
        setSelectedId(mostSuspicious?.id ?? data.records[0]?.id ?? null)
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : String(reason)))
  }, [])

  useEffect(() => {
    if (!audit || !mapDivRef.current) return
    const map = L.map(mapDivRef.current).setView([36.5, 136], 5)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
    }).addTo(map)
    map.on('click', event => {
      const lat = Number(event.latlng.lat.toFixed(7))
      const lng = Number(event.latlng.lng.toFixed(7))
      setOverrideLat(String(lat))
      setOverrideLng(String(lng))
      setDraftCoordinate({ lat, lng })
      setSaveState('idle')
      setSaveError(null)
    })
    mapRef.current = map
    return () => {
      draftMarkerRef.current = null
      map.remove()
      mapRef.current = null
    }
  }, [audit])

  const records = useMemo(() => {
    if (!audit) return []
    const needle = search.trim().toLowerCase()
    const filtered = audit.records.filter(record => {
      if (status !== 'all' && record.status !== status) return false
      if (!needle) return true
      return `${record.id} ${record.title} ${record.prefecture ?? ''} ${record.city ?? ''} ${record.address}`
        .toLowerCase()
        .includes(needle)
    })
    return filtered.sort((left, right) => {
      if (sortOrder === 'suspicious') {
        return reviewPriority(right).score - reviewPriority(left).score
          || Number(left.id) - Number(right.id)
      }
      if (sortOrder === 'score') {
        return (left.selected?.score ?? -1) - (right.selected?.score ?? -1)
          || Number(left.id) - Number(right.id)
      }
      if (sortOrder === 'distance') {
        return (right.old_distance_km ?? -1) - (left.old_distance_km ?? -1)
          || Number(left.id) - Number(right.id)
      }
      return Number(left.id) - Number(right.id)
    })
  }, [audit, search, sortOrder, status])

  const selected = audit?.records.find(record => record.id === selectedId) ?? null

  useEffect(() => {
    if (!selected) return
    setOverrideLat(String(selected.override?.lat ?? selected.selected?.lat ?? ''))
    setOverrideLng(String(selected.override?.lng ?? selected.selected?.lng ?? ''))
    setOverrideOfficialUrl(selected.override?.official_url ?? selected.override?.source_url ?? '')
    setOverrideNote(selected.override?.note ?? '')
    setDraftCoordinate(null)
    setSaveState('idle')
    setSaveError(null)
  }, [selectedId, selected?.id])

  async function saveOverride() {
    if (!selected) return
    setSaveState('saving')
    setSaveError(null)
    try {
      const response = await fetch('/__editor/data/gmanhole-override', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: selected.id,
          lat: overrideLat,
          lng: overrideLng,
          official_url: overrideOfficialUrl,
          note: overrideNote,
        }),
      })
      const result = await response.json() as {
        ok?: boolean
        audit?: GeocodeAudit
        patch?: SemanticPatch
        error?: string
      }
      if (!response.ok || !result.audit) throw new Error(result.error ?? `HTTP ${response.status}`)
      setAudit(result.audit)
      setDraftCoordinate(null)
      setSaveState('saved')
      if (result.patch) onPatchSaved?.(result.patch)
    } catch (reason) {
      setSaveState('idle')
      setSaveError(reason instanceof Error ? reason.message : String(reason))
    }
  }

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
      ).addTo(map).bindPopup(candidatePopup(candidate))
      layersRef.current.push(marker)
      points.push([candidate.lat, candidate.lng])
    })

    if (points.length === 1) map.setView(points[0], 17)
    else if (points.length > 1) map.fitBounds(L.latLngBounds(points).pad(0.2), { maxZoom: 17 })
  }, [selected])

  useEffect(() => {
    const map = mapRef.current
    draftMarkerRef.current?.remove()
    draftMarkerRef.current = null
    if (!map || !draftCoordinate) return
    draftMarkerRef.current = L.marker(
      [draftCoordinate.lat, draftCoordinate.lng],
      { icon: markerIcon('仮', '#0891b2', 30), zIndexOffset: 700 },
    ).addTo(map).bindPopup(
      `保存前の座標<br>${draftCoordinate.lat.toFixed(7)}, ${draftCoordinate.lng.toFixed(7)}`,
    ).openPopup()
  }, [draftCoordinate])

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
        <select value={sortOrder} onChange={event => setSortOrder(event.target.value as SortOrder)}>
          <option value="suspicious">要確認度が高い順</option>
          <option value="score">採用scoreが低い順</option>
          <option value="distance">旧座標から遠い順</option>
          <option value="id">ID順</option>
        </select>
        <span style={{ color: '#6b7280' }}>{records.length}件</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 42%) 1fr', gap: 16 }}>
        <div style={{ maxHeight: 'calc(100vh - 190px)', overflow: 'auto', background: 'white', border: '1px solid #e5e7eb', borderRadius: 8 }}>
          <table className="table">
            <thead>
              <tr><th>ID</th><th>設置場所</th><th>状態 / 要確認</th><th>採用</th></tr>
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
                  <td>
                    <div>{statusLabel(record.status)}</div>
                    <strong style={{ color: reviewPriority(record).score >= 40 ? '#dc2626' : '#6b7280' }}>
                      {reviewPriority(record).score > 0 ? reviewPriority(record).score : '—'}
                    </strong>
                    <div style={{ color: '#6b7280', fontSize: 11 }}>
                      {reviewPriority(record).reasons.join(' / ')}
                    </div>
                  </td>
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
          <div style={{ color: '#475569', fontSize: 12, marginTop: -6, marginBottom: 12 }}>
            地図をクリックすると、緯度・経度欄へ反映して「仮」マーカーを表示します。保存ボタンを押すまで確定されません。
          </div>
          {selected && (
            <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <h3>#{selected.id} {selected.title}</h3>
                  <div style={{ color: '#6b7280', marginTop: 4 }}>{selected.address}</div>
                </div>
                {selected.detail_url && <a href={selected.detail_url} target="_blank" rel="noreferrer">公式ページ</a>}
              </div>

              {selected.override && (
                <div style={{ marginTop: 12, padding: 10, borderRadius: 6, background: '#ecfeff', border: '1px solid #a5f3fc' }}>
                  <strong>手動管理データ</strong>
                  <div style={{ marginTop: 4 }}>
                    表示: {selected.override.status ?? '未指定'}
                    {' / '}設置状態: {selected.override.installation_status ?? '未指定'}
                    {selected.override.installed_at && ` / 設置日: ${selected.override.installed_at}`}
                    {selected.override.verified_at && ` / 確認日: ${selected.override.verified_at}`}
                  </div>
                  {selected.override.note && <div style={{ marginTop: 4 }}>{selected.override.note}</div>}
                  {(selected.override.official_url || selected.override.source_url) && (
                    <div style={{ marginTop: 4 }}>
                      <a href={selected.override.official_url ?? selected.override.source_url} target="_blank" rel="noreferrer">公式・確認元URLを開く</a>
                    </div>
                  )}
                </div>
              )}

              <div style={{ marginTop: 12, padding: 12, borderRadius: 6, background: '#f8fafc', border: '1px solid #cbd5e1' }}>
                <strong>座標を強制変更</strong>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
                  <label>
                    <div style={{ fontSize: 12, color: '#475569' }}>緯度</div>
                    <input
                      type="number"
                      step="any"
                      min="-90"
                      max="90"
                      value={overrideLat}
                      onChange={event => setOverrideLat(event.target.value)}
                      style={{ width: '100%' }}
                    />
                  </label>
                  <label>
                    <div style={{ fontSize: 12, color: '#475569' }}>経度</div>
                    <input
                      type="number"
                      step="any"
                      min="-180"
                      max="180"
                      value={overrideLng}
                      onChange={event => setOverrideLng(event.target.value)}
                      style={{ width: '100%' }}
                    />
                  </label>
                </div>
                <label style={{ display: 'block', marginTop: 8 }}>
                  <div style={{ fontSize: 12, color: '#475569' }}>公式・確認元URL</div>
                  <input
                    type="url"
                    placeholder="https://..."
                    value={overrideOfficialUrl}
                    onChange={event => setOverrideOfficialUrl(event.target.value)}
                    style={{ width: '100%' }}
                  />
                </label>
                <label style={{ display: 'block', marginTop: 8 }}>
                  <div style={{ fontSize: 12, color: '#475569' }}>確認メモ</div>
                  <input
                    value={overrideNote}
                    onChange={event => setOverrideNote(event.target.value)}
                    placeholder="現地写真や公式ページで確認した内容"
                    style={{ width: '100%' }}
                  />
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10 }}>
                  <button type="button" onClick={saveOverride} disabled={saveState === 'saving'}>
                    {saveState === 'saving' ? '保存・反映中…' : '強制座標を保存して反映'}
                  </button>
                  {saveState === 'saved' && <span style={{ color: '#15803d' }}>保存しました</span>}
                  {saveError && <span style={{ color: '#dc2626' }}>{saveError}</span>}
                </div>
              </div>

              <div style={{ marginTop: 12, padding: 10, borderRadius: 6, background: '#fff7ed', border: '1px solid #fed7aa' }}>
                <strong>要確認度 {reviewPriority(selected).score > 0 ? reviewPriority(selected).score : '—'}</strong>
                <div style={{ marginTop: 4 }}>{reviewPriority(selected).reasons.join(' / ')}</div>
                <div style={{ marginTop: 4, color: '#6b7280', fontSize: 11 }}>
                  低スコア、住所省略・名称検索、旧座標からの距離をもとにした目視確認用の順位です。
                </div>
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
