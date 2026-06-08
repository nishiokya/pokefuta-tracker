import { useState, useRef, useEffect } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { PokefutaRecord } from '../../semantic/semanticPatch'

export type TagRow = {
  key: string
  emoji: string
  label: string
  priority: number
  count: number
  editable: boolean
}

export type ManholeItem = {
  id: string
  record: PokefutaRecord | undefined
  badgeLabel?: string
}

type Props = {
  tagRow: TagRow
  manholeList: ManholeItem[]
  editable: boolean
  onBack: () => void
  onNavigateToEdit: (manholeId: string) => void
}

function makeIcon(selected: boolean) {
  const color = selected ? '#ef4444' : '#3b82f6'
  return L.divIcon({
    className: '',
    html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,0.5)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -10],
  })
}

function esc(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

export function TagDetailView({ tagRow, manholeList, editable, onBack, onNavigateToEdit }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const mapDivRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markersRef = useRef<Map<string, L.Marker>>(new Map())
  const itemRefsRef = useRef<Map<string, HTMLDivElement>>(new Map())

  const plottable = manholeList.filter(i => i.record?.lat != null)

  // Initialize map once
  useEffect(() => {
    if (!mapDivRef.current) return
    const map = L.map(mapDivRef.current).setView([36.5, 136.0], 5)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map)
    mapRef.current = map

    plottable.forEach(item => {
      const r = item.record!
      const popupHtml = [
        `<b>#${r.id}</b> ${esc(r.prefecture)} ${esc(r.city)}`,
        `<span style="font-size:11px">${esc(r.address)}</span>`,
        item.badgeLabel ? `<span style="font-size:11px;color:#7c3aed">${esc(item.badgeLabel)}</span>` : '',
      ].filter(Boolean).join('<br>')

      const marker = L.marker([r.lat, r.lng], { icon: makeIcon(false) })
        .addTo(map)
        .bindPopup(popupHtml)
        .on('click', () => setSelectedId(cur => cur === r.id ? null : r.id))
      markersRef.current.set(r.id, marker)
    })

    if (plottable.length > 1) {
      const bounds = L.latLngBounds(plottable.map(i => [i.record!.lat, i.record!.lng]))
      map.fitBounds(bounds, { padding: [30, 30] })
    } else if (plottable.length === 1) {
      map.setView([plottable[0].record!.lat, plottable[0].record!.lng], 10)
    }

    return () => {
      map.remove()
      mapRef.current = null
      markersRef.current.clear()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Sync marker color and popup when selection changes
  useEffect(() => {
    markersRef.current.forEach((marker, id) => {
      marker.setIcon(makeIcon(id === selectedId))
    })
    if (selectedId) {
      const marker = markersRef.current.get(selectedId)
      marker?.openPopup()
      const item = manholeList.find(i => i.id === selectedId)
      if (item?.record) mapRef.current?.panTo([item.record.lat, item.record.lng])
      const el = itemRefsRef.current.get(selectedId)
      el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [selectedId, manholeList])

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '8px 0 12px',
        borderBottom: '1px solid #e2e8f0',
        flexShrink: 0,
        flexWrap: 'wrap',
      }}>
        <button
          onClick={onBack}
          style={{ padding: '5px 14px', fontSize: 13, background: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: 6, cursor: 'pointer', whiteSpace: 'nowrap' }}
        >
          ← 一覧に戻る
        </button>
        <span style={{ fontSize: 22 }}>{tagRow.emoji}</span>
        <h3 style={{ margin: 0, fontSize: 17 }}>{tagRow.label.replace(/\{[^}]+\}/g, '…')}</h3>
        <code style={{ fontSize: 12, color: '#64748b', background: '#f1f5f9', padding: '2px 7px', borderRadius: 4 }}>{tagRow.key}</code>
        <span style={{ fontSize: 14, color: '#6b7280' }}>{manholeList.length}件</span>
        {!editable && (
          <span style={{ fontSize: 11, color: '#94a3b8', background: '#f1f5f9', padding: '2px 8px', borderRadius: 4 }}>自動計算・読み取り専用</span>
        )}
      </div>

      {/* Body: list (left) + map (right) */}
      <div style={{ display: 'flex', height: 'calc(100vh - 180px)', marginTop: 12 }}>
        {/* Left: scrollable manhole list */}
        <div style={{ width: 320, flexShrink: 0, overflowY: 'auto', borderRight: '1px solid #e2e8f0', paddingRight: 8 }}>
          {manholeList.length === 0 ? (
            <div style={{ padding: 24, color: '#9ca3af', textAlign: 'center' }}>マンホールがありません</div>
          ) : (
            manholeList.map(item => {
              const isSelected = item.id === selectedId
              return (
                <div
                  key={item.id}
                  ref={el => { if (el) itemRefsRef.current.set(item.id, el); else itemRefsRef.current.delete(item.id) }}
                  onClick={() => setSelectedId(cur => cur === item.id ? null : item.id)}
                  style={{
                    padding: '10px 12px',
                    marginBottom: 2,
                    borderRadius: 6,
                    cursor: 'pointer',
                    background: isSelected ? '#eff6ff' : '#fff',
                    outline: isSelected ? '2px solid #3b82f6' : '1px solid #f1f5f9',
                    outlineOffset: '-1px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                    <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#94a3b8', flexShrink: 0 }}>#{item.id}</span>
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#1e293b' }}>
                      {item.record?.title ?? '—'}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: '#64748b', marginTop: 3 }}>
                    {item.record?.prefecture} {item.record?.city}
                  </div>
                  {item.badgeLabel && (
                    <div style={{ fontSize: 11, color: '#7c3aed', marginTop: 2 }}>{item.badgeLabel}</div>
                  )}
                  {editable && (
                    <button
                      onClick={e => { e.stopPropagation(); onNavigateToEdit(item.id) }}
                      style={{ marginTop: 5, padding: '2px 8px', fontSize: 11, borderRadius: 4, border: '1px solid #c4b5d4', background: '#f8f4ff', color: '#7c3aed', cursor: 'pointer' }}
                    >
                      タグを編集
                    </button>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* Right: Leaflet map */}
        <div ref={mapDivRef} style={{ flex: 1, borderRadius: '0 0 8px 0' }} />
      </div>
    </div>
  )
}
