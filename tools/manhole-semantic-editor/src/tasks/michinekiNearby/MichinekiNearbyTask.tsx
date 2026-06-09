import { useState, useEffect, useRef, useMemo } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { PokefutaRecord, ManholeTitlesJson, SemanticPatch } from '../../semantic/semanticPatch'
import { newPatchId } from '../../util'

type MichinekiStation = { id: string; name: string; lat: number; lng: number }

type Pair = {
  pf: PokefutaRecord
  mi: MichinekiStation
  distM: number
}

function haversineM(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6_371_000
  const p1 = (lat1 * Math.PI) / 180
  const p2 = (lat2 * Math.PI) / 180
  const dp = ((lat2 - lat1) * Math.PI) / 180
  const dl = ((lng2 - lng1) * Math.PI) / 180
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return R * 2 * Math.asin(Math.sqrt(a))
}

function makeIcon(color: string, shape: 'circle' | 'square' = 'circle') {
  const radius = shape === 'circle' ? '50%' : '3px'
  return L.divIcon({
    className: '',
    html: `<div style="width:14px;height:14px;border-radius:${radius};background:${color};border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,0.5)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  })
}

function esc(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

type Props = {
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSaveMany: (patches: SemanticPatch[]) => Promise<void>
  saving: boolean
}

export function MichinekiNearbyTask({ records, titles, onSaveMany, saving }: Props) {
  const [stations, setStations] = useState<MichinekiStation[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [showFilter, setShowFilter] = useState<'all' | 'linked' | 'unlinked'>('all')
  const [pending, setPending] = useState<Map<string, boolean>>(new Map())
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  const mapDivRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerGroupRef = useRef<L.LayerGroup | null>(null)

  useEffect(() => {
    fetch('/__editor/data/michineki')
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json() as Promise<MichinekiStation[]> })
      .then(setStations)
      .catch(e => setLoadError(String(e)))
  }, [])

  const pairs = useMemo((): Pair[] => {
    if (stations.length === 0) return []
    const result: Pair[] = []
    for (const pf of records) {
      if (pf.status !== 'active') continue
      for (const mi of stations) {
        const d = haversineM(pf.lat, pf.lng, mi.lat, mi.lng)
        if (d < 300) result.push({ pf, mi, distM: Math.round(d) })
      }
    }
    return result.sort((a, b) => a.distM - b.distM)
  }, [records, stations])

  const isLinked = (pfId: string): boolean => {
    if (pending.has(pfId)) return pending.get(pfId)!
    return (titles.manholes[pfId]?.tags ?? []).includes('roadside')
  }

  const filtered = useMemo(() => {
    const lower = search.toLowerCase()
    const result = pairs.filter(p => {
      if (showFilter === 'linked' && !isLinked(p.pf.id)) return false
      if (showFilter === 'unlinked' && isLinked(p.pf.id)) return false
      if (!lower) return true
      return (
        p.pf.title.toLowerCase().includes(lower) ||
        p.pf.pokemons.some(pk => pk.includes(lower)) ||
        p.mi.name.toLowerCase().includes(lower) ||
        p.pf.prefecture.includes(lower)
      )
    })
    // 未紐づけを先、紐づけ済みを後（同一グループ内は距離順）
    result.sort((a, b) => {
      const al = isLinked(a.pf.id) ? 1 : 0
      const bl = isLinked(b.pf.id) ? 1 : 0
      return al !== bl ? al - bl : a.distM - b.distM
    })
    return result
  }, [pairs, showFilter, search, pending, titles])

  // Map init
  useEffect(() => {
    if (!mapDivRef.current) return
    const map = L.map(mapDivRef.current).setView([36.5, 136.0], 5)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map)
    const lg = L.layerGroup().addTo(map)
    mapRef.current = map
    layerGroupRef.current = lg
    return () => { map.remove(); mapRef.current = null; layerGroupRef.current = null }
  }, [])

  // Rebuild map layers when filtered/selected changes
  useEffect(() => {
    const map = mapRef.current
    const lg = layerGroupRef.current
    if (!map || !lg) return
    lg.clearLayers()

    filtered.forEach((pair, i) => {
      const linked = isLinked(pair.pf.id)
      const isSelected = selectedIdx === i
      const pfColor = isSelected ? '#ef4444' : linked ? '#22c55e' : '#3b82f6'
      const miColor = isSelected ? '#f97316' : '#7c3aed'

      const pfM = L.marker([pair.pf.lat, pair.pf.lng], { icon: makeIcon(pfColor) })
        .bindPopup(`<b>#${pair.pf.id}</b> ${esc(pair.pf.title)}<br><small>${esc(pair.pf.pokemons.join(', '))}</small>`)
        .on('click', () => setSelectedIdx(idx => idx === i ? null : i))
      const miM = L.marker([pair.mi.lat, pair.mi.lng], { icon: makeIcon(miColor, 'square') })
        .bindPopup(`<b>${esc(pair.mi.name)}</b><br><small>${pair.distM}m</small>`)
      const line = L.polyline([[pair.pf.lat, pair.pf.lng], [pair.mi.lat, pair.mi.lng]], {
        color: isSelected ? '#f97316' : '#94a3b8',
        weight: isSelected ? 3 : 1.5,
        opacity: isSelected ? 1 : 0.5,
        dashArray: '4,4',
      })
      lg.addLayer(line)
      lg.addLayer(pfM)
      lg.addLayer(miM)
    })

    if (selectedIdx !== null && filtered[selectedIdx]) {
      const p = filtered[selectedIdx]
      map.flyTo([p.pf.lat, p.pf.lng], 17, { duration: 0.6 })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, selectedIdx])

  function togglePending(pfId: string) {
    setPending(prev => {
      const next = new Map(prev)
      const base = (titles.manholes[pfId]?.tags ?? []).includes('roadside')
      if (next.has(pfId)) {
        next.delete(pfId)
      } else {
        next.set(pfId, !base)
      }
      return next
    })
  }

  const dirtyIds = [...pending.entries()].filter(([id, val]) => {
    const base = (titles.manholes[id]?.tags ?? []).includes('roadside')
    return val !== base
  })

  async function handleSave() {
    setSaveError(null)
    const patches: SemanticPatch[] = []
    for (const [id, linked] of dirtyIds) {
      patches.push({
        id: newPatchId(),
        createdAt: new Date().toISOString(),
        taskType: 'michineki_nearby',
        operation: linked ? 'add_tags' : 'remove_tags',
        target: 'manholes',
        manholeIds: [parseInt(id, 10)],
        payload: { tags: ['roadside'] },
      })
    }
    try {
      await onSaveMany(patches)
      setPending(new Map())
    } catch (e) {
      setSaveError(String(e))
    }
  }

  if (loadError) {
    return <div className="error-banner">道の駅データ読み込みエラー: {loadError}</div>
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div>
          <h2 style={{ margin: 0 }}>道の駅 × ポケふた 300m圏内</h2>
          {stations.length === 0 ? (
            <p style={{ margin: '4px 0 0', fontSize: 13, color: '#6b7280' }}>道の駅データを読み込んでいます…</p>
          ) : (
            <p style={{ margin: '4px 0 0', fontSize: 13, color: '#6b7280' }}>
              全{pairs.length}ペア（300m以内）— 「紐づけ」= <code>roadside</code> タグ
            </p>
          )}
        </div>
        {dirtyIds.length > 0 && (
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? '保存中…' : `${dirtyIds.length}件を保存`}
          </button>
        )}
      </div>

      {saveError && (
        <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 6, padding: 12, marginBottom: 12, color: '#dc2626' }}>
          {saveError}
        </div>
      )}

      {stations.length > 0 && (
        <div className="filter-bar" style={{ marginBottom: 12 }}>
          <input
            placeholder="地名・ポケモン名・道の駅名で絞り込み"
            value={search}
            onChange={e => { setSearch(e.target.value); setSelectedIdx(null) }}
            style={{ width: 280 }}
          />
          <select value={showFilter} onChange={e => { setShowFilter(e.target.value as typeof showFilter); setSelectedIdx(null) }}>
            <option value="all">全件 ({pairs.length})</option>
            <option value="linked">紐づけ済み</option>
            <option value="unlinked">未紐づけ</option>
          </select>
          <span style={{ fontSize: 13, color: '#6b7280' }}>{filtered.length}件表示</span>
        </div>
      )}

      {stations.length > 0 && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 8, fontSize: 12, color: '#6b7280', alignItems: 'center' }}>
          <span>凡例:</span>
          {([['#22c55e', '●', '紐づけ済み（ポケふた）'], ['#3b82f6', '●', '未紐づけ（ポケふた）'], ['#ef4444', '●', '選択中（ポケふた）'], ['#7c3aed', '■', '道の駅']] as [string, string, string][]).map(([c, s, l]) => (
            <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <span style={{ color: c }}>{s}</span>{l}
            </span>
          ))}
        </div>
      )}

      <div ref={mapDivRef} style={{ height: 320, borderRadius: 8, border: '1px solid #e5e7eb', marginBottom: 12, overflow: 'hidden' }} />

      {stations.length > 0 && <table className="table">
        <thead>
          <tr>
            <th style={{ width: 48 }}>距離</th>
            <th>ポケふた</th>
            <th>道の駅</th>
            <th style={{ width: 90 }}>roadside</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((pair, i) => {
            const linked = isLinked(pair.pf.id)
            const isDirty = pending.has(pair.pf.id)
            const isSelected = selectedIdx === i
            return (
              <tr
                key={`${pair.pf.id}-${pair.mi.id}`}
                onClick={() => setSelectedIdx(idx => idx === i ? null : i)}
                style={{
                  cursor: 'pointer',
                  background: isSelected ? '#eff6ff' : isDirty ? '#fefce8' : undefined,
                  outline: isSelected ? '2px solid #3b82f6' : undefined,
                  outlineOffset: '-1px',
                }}
              >
                <td style={{ fontWeight: 600, color: pair.distM < 20 ? '#ef4444' : pair.distM < 50 ? '#f97316' : '#6b7280', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                  {pair.distM}m
                </td>
                <td>
                  <div style={{ fontWeight: 500 }}>#{pair.pf.id} {pair.pf.prefecture} {pair.pf.city}</div>
                  <div style={{ fontSize: 11, color: '#6b7280' }}>{pair.pf.pokemons.join(', ')}</div>
                </td>
                <td>
                  <div>{pair.mi.name}</div>
                </td>
                <td onClick={e => e.stopPropagation()}>
                  <button
                    className={`tag ${linked ? 'tag-active' : 'tag-inactive'}`}
                    style={{ fontWeight: isDirty ? 700 : undefined }}
                    onClick={() => togglePending(pair.pf.id)}
                  >
                    {linked ? '✓ 紐づけ済' : '＋ 紐づける'}
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>}
    </div>
  )
}
