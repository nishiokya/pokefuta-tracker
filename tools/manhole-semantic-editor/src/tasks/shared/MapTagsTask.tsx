import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { PokefutaRecord, ManholeTitlesJson, SemanticPatch, ManholeEntry, TaskType } from '../../semantic/semanticPatch'
import { validatePatch } from '../../semantic/semanticPatchValidator'
import { newPatchId } from '../../util'

const PAGE_SIZE = 10

const PREF_ORDER = [
  '北海道','青森県','岩手県','宮城県','秋田県','山形県','福島県',
  '茨城県','栃木県','群馬県','埼玉県','千葉県','東京都','神奈川県',
  '新潟県','富山県','石川県','福井県','山梨県','長野県','岐阜県',
  '静岡県','愛知県','三重県','滋賀県','京都府','大阪府','兵庫県',
  '奈良県','和歌山県','鳥取県','島根県','岡山県','広島県','山口県',
  '徳島県','香川県','愛媛県','高知県','福岡県','佐賀県','長崎県',
  '熊本県','大分県','宮崎県','鹿児島県','沖縄県',
]

function sortByPrefCode(prefs: string[]): string[] {
  return [...prefs].sort((a, b) => {
    const ai = PREF_ORDER.indexOf(a)
    const bi = PREF_ORDER.indexOf(b)
    if (ai === -1 && bi === -1) return a.localeCompare(b, 'ja')
    if (ai === -1) return 1
    if (bi === -1) return -1
    return ai - bi
  })
}

function makeIcon(color: string) {
  return L.divIcon({
    className: '',
    html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,0.5)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -10],
  })
}

export type HintFilter = {
  label: string
  fn: (r: PokefutaRecord, entry: ManholeEntry | undefined) => boolean
  defaultOn?: boolean
}

export type MapTagsTaskProps = {
  title: string
  taskType: TaskType
  tags: readonly string[]
  tagLabels: Record<string, string>
  hintFilter?: HintFilter
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSaveMany: (patches: SemanticPatch[]) => Promise<void>
  saving: boolean
}

export function MapTagsTask({
  title,
  taskType,
  tags,
  tagLabels,
  hintFilter,
  records,
  titles,
  onSaveMany,
  saving,
}: MapTagsTaskProps) {
  const [search, setSearch] = useState('')
  const [prefFilter, setPrefFilter] = useState('')
  const [showFilter, setShowFilter] = useState<'all' | 'has_tag' | 'no_tag'>('all')
  const [hintOn, setHintOn] = useState(hintFilter?.defaultOn ?? false)
  const [pending, setPending] = useState<Map<string, Set<string>>>(new Map())
  const [saveError, setSaveError] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const mapDivRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markersRef = useRef<Map<string, L.Marker>>(new Map())

  const prefectures = useMemo(
    () => sortByPrefCode([...new Set(records.map(r => r.prefecture))]),
    [records]
  )

  const filtered = useMemo(() => {
    return records.filter(r => {
      if (r.status !== 'active') return false
      if (prefFilter && r.prefecture !== prefFilter) return false
      if (search && !`${r.id} ${r.prefecture} ${r.city} ${r.address}`.includes(search)) return false
      if (hintFilter && hintOn && !hintFilter.fn(r, titles.manholes[r.id])) return false
      const currentTags = titles.manholes[r.id]?.tags ?? []
      const hasAnyTag = tags.some(t => currentTags.includes(t))
      if (showFilter === 'has_tag' && !hasAnyTag) return false
      if (showFilter === 'no_tag' && hasAnyTag) return false
      return true
    })
  }, [records, titles, prefFilter, search, showFilter, hintFilter, hintOn, tags])

  useEffect(() => { setPage(0); setSelectedId(null) }, [filtered])

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE) || 1
  const pageItems = useMemo(
    () => filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE),
    [filtered, page]
  )

  // Initialize map
  useEffect(() => {
    if (!mapDivRef.current) return
    const map = L.map(mapDivRef.current).setView([36.5, 136.0], 5)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map)
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Rebuild markers on page change
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    markersRef.current.forEach(m => m.remove())
    markersRef.current.clear()

    if (pageItems.length === 0) return

    pageItems.forEach(r => {
      const marker = L.marker([r.lat, r.lng], { icon: makeIcon('#3b82f6') })
        .addTo(map)
        .bindPopup(`<b>#${r.id}</b> ${r.prefecture} ${r.city}<br><span style="font-size:11px">${r.address}</span>`)
        .on('click', () => setSelectedId(id => id === r.id ? null : r.id))
      markersRef.current.set(r.id, marker)
    })

    map.setView([pageItems[0].lat, pageItems[0].lng], 18)

    return () => {
      markersRef.current.forEach(m => m.remove())
      markersRef.current.clear()
    }
  }, [pageItems])

  // Sync marker icons when selection or pending changes
  useEffect(() => {
    markersRef.current.forEach((marker, id) => {
      const base = titles.manholes[id]?.tags ?? []
      const currentTags = pending.has(id) ? pending.get(id)! : new Set(base)
      const hasTag = tags.some(t => currentTags.has(t))
      const isSelected = id === selectedId
      marker.setIcon(makeIcon(isSelected ? '#ef4444' : hasTag ? '#22c55e' : '#3b82f6'))
      if (isSelected) marker.openPopup()
    })

    if (selectedId) {
      const sel = pageItems.find(r => r.id === selectedId)
      if (sel) mapRef.current?.panTo([sel.lat, sel.lng])
    }
  }, [selectedId, pending, pageItems, titles, tags])

  function getEffectiveTags(id: string): Set<string> {
    if (pending.has(id)) return new Set(pending.get(id))
    return new Set(titles.manholes[id]?.tags ?? [])
  }

  function toggleTag(id: string, tag: string) {
    setPending(prev => {
      const next = new Map(prev)
      const base = new Set(titles.manholes[id]?.tags ?? [])
      const current = next.has(id) ? new Set(next.get(id)) : new Set(base)
      if (current.has(tag)) current.delete(tag)
      else current.add(tag)
      if ([...current].sort().join() === [...base].sort().join()) {
        next.delete(id)
      } else {
        next.set(id, current)
      }
      return next
    })
  }

  async function handleSaveAll() {
    setSaveError(null)
    const patches: SemanticPatch[] = []

    for (const [id, tags_] of pending.entries()) {
      const base = new Set(titles.manholes[id]?.tags ?? [])
      const added = [...tags_].filter(t => !base.has(t))
      const removed = [...base].filter(t => !tags_.has(t))

      if (added.length > 0) {
        const patch: SemanticPatch = {
          id: newPatchId(),
          createdAt: new Date().toISOString(),
          taskType,
          operation: 'add_tags',
          target: 'manholes',
          manholeIds: [parseInt(id, 10)],
          payload: { tags: added },
        }
        const v = validatePatch(patch, titles)
        if (!v.valid) { setSaveError(v.errors.join('\n')); return }
        patches.push(patch)
      }
      if (removed.length > 0) {
        patches.push({
          id: newPatchId(),
          createdAt: new Date().toISOString(),
          taskType,
          operation: 'remove_tags',
          target: 'manholes',
          manholeIds: [parseInt(id, 10)],
          payload: { tags: removed },
        })
      }
    }

    if (patches.length > 0) await onSaveMany(patches)
    setPending(new Map())
  }

  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyAddress = useCallback((e: React.MouseEvent, id: string, address: string) => {
    e.stopPropagation()
    navigator.clipboard.writeText(address).then(() => {
      setCopiedId(id)
      setTimeout(() => setCopiedId(c => c === id ? null : c), 1500)
    })
  }, [])

  const pendingCount = pending.size

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>{title}</h2>
        {pendingCount > 0 && (
          <button className="btn btn-primary" onClick={handleSaveAll} disabled={saving}>
            {saving ? '保存中…' : `${pendingCount}件を保存`}
          </button>
        )}
      </div>

      {saveError && (
        <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 6, padding: 12, marginBottom: 12, color: '#dc2626' }}>
          {saveError}
        </div>
      )}

      <div className="filter-bar">
        <input
          placeholder="ID / 住所 / 市区町村で絞り込み"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 240 }}
        />
        <select value={prefFilter} onChange={e => setPrefFilter(e.target.value)}>
          <option value="">全都道府県</option>
          {prefectures.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={showFilter} onChange={e => setShowFilter(e.target.value as typeof showFilter)}>
          <option value="all">全件</option>
          <option value="has_tag">タグあり</option>
          <option value="no_tag">タグなし</option>
        </select>
        {hintFilter && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={hintOn} onChange={e => setHintOn(e.target.checked)} />
            {hintFilter.label}
          </label>
        )}
        <span style={{ color: '#6b7280', fontSize: 13 }}>{filtered.length}件</span>
      </div>

      <div style={{ display: 'flex', gap: 16, marginBottom: 8, fontSize: 12, color: '#6b7280', alignItems: 'center' }}>
        <span>凡例:</span>
        {[['#3b82f6', 'タグなし'], ['#22c55e', 'タグあり'], ['#ef4444', '選択中']].map(([color, label]) => (
          <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, display: 'inline-block', border: '1px solid white', boxShadow: '0 0 2px rgba(0,0,0,0.4)' }} />
            {label}
          </span>
        ))}
        <span style={{ marginLeft: 'auto' }}>マーカーをクリックで詳細</span>
      </div>

      <div ref={mapDivRef} style={{ height: 340, borderRadius: 8, border: '1px solid #e5e7eb', marginBottom: 12, overflow: 'hidden' }} />

      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 50 }}>ID</th>
            <th>場所</th>
            <th>住所</th>
            <th>タグ</th>
          </tr>
        </thead>
        <tbody>
          {pageItems.map(r => {
            const effectiveTags = getEffectiveTags(r.id)
            const isDirty = pending.has(r.id)
            const isSelected = r.id === selectedId
            return (
              <tr
                key={r.id}
                onClick={() => setSelectedId(id => id === r.id ? null : r.id)}
                style={{
                  background: isSelected ? '#eff6ff' : isDirty ? '#fefce8' : undefined,
                  cursor: 'pointer',
                  outline: isSelected ? '2px solid #3b82f6' : undefined,
                  outlineOffset: '-1px',
                }}
              >
                <td style={{ fontFamily: 'monospace' }}>{r.id}</td>
                <td>
                  <div>{r.prefecture} {r.city}</div>
                  {titles.manholes[r.id]?.building && (
                    <div style={{ fontSize: 11, color: '#6b7280' }}>{titles.manholes[r.id].building}</div>
                  )}
                </td>
                <td style={{ fontSize: 12, maxWidth: 200, wordBreak: 'break-all' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 4 }}>
                    <span style={{ flex: 1 }}>{r.address}</span>
                    <button
                      onClick={e => copyAddress(e, r.id, r.address)}
                      title="住所をコピー"
                      style={{
                        flexShrink: 0,
                        padding: '1px 5px',
                        fontSize: 11,
                        lineHeight: 1.4,
                        background: copiedId === r.id ? '#d1fae5' : '#f3f4f6',
                        color: copiedId === r.id ? '#059669' : '#374151',
                        border: '1px solid',
                        borderColor: copiedId === r.id ? '#6ee7b7' : '#d1d5db',
                        borderRadius: 4,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {copiedId === r.id ? '✓' : '📋'}
                    </button>
                  </div>
                </td>
                <td onClick={e => e.stopPropagation()}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {tags.map(tag => (
                      <button
                        key={tag}
                        className={`tag ${effectiveTags.has(tag) ? 'tag-active' : 'tag-inactive'}`}
                        onClick={() => toggleTag(r.id, tag)}
                        title={tag}
                      >
                        {tagLabels[tag] ?? tag}
                      </button>
                    ))}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16, marginTop: 12 }}>
        <button
          className="btn"
          style={{ padding: '6px 14px', background: '#f3f4f6', fontSize: 13 }}
          onClick={() => { setPage(p => p - 1); setSelectedId(null) }}
          disabled={page === 0}
        >
          ← 前へ
        </button>
        <span style={{ fontSize: 13, color: '#6b7280' }}>
          {page + 1} / {totalPages}
          <span style={{ marginLeft: 8, color: '#9ca3af' }}>
            （{filtered.length}件中 {page * PAGE_SIZE + 1}〜{Math.min((page + 1) * PAGE_SIZE, filtered.length)}件）
          </span>
        </span>
        <button
          className="btn"
          style={{ padding: '6px 14px', background: '#f3f4f6', fontSize: 13 }}
          onClick={() => { setPage(p => p + 1); setSelectedId(null) }}
          disabled={page >= totalPages - 1}
        >
          次へ →
        </button>
      </div>
    </div>
  )
}
