import { useState, useMemo } from 'react'
import type { PokefutaRecord, ManholeTitlesJson, SemanticPatch } from '../../semantic/semanticPatch'
import { validatePatch } from '../../semantic/semanticPatchValidator'
import { newPatchId } from '../../util'

const LOCATION_TAGS = ['seaside', 'beach', 'lakeside', 'river', 'remote_island'] as const
type LocationTag = (typeof LOCATION_TAGS)[number]

const TAG_LABEL: Record<LocationTag, string> = {
  seaside: '🌊 海沿い',
  beach: '🏖 ビーチ',
  lakeside: '🏞 湖畔',
  river: '🌊 川沿い',
  remote_island: '🏝 離島',
}

type Props = {
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSave: (patch: SemanticPatch) => Promise<void>
  saving: boolean
}

export function AssignLocationTagsTask({ records, titles, onSave, saving }: Props) {
  const [search, setSearch] = useState('')
  const [prefFilter, setPrefFilter] = useState('')
  const [showFilter, setShowFilter] = useState<'all' | 'has_tag' | 'no_tag'>('all')
  const [pending, setPending] = useState<Map<string, Set<string>>>(new Map())
  const [saveError, setSaveError] = useState<string | null>(null)

  const prefectures = useMemo(
    () => [...new Set(records.map(r => r.prefecture))].sort(),
    [records]
  )

  const filtered = useMemo(() => {
    return records.filter(r => {
      if (r.status !== 'active') return false
      if (prefFilter && r.prefecture !== prefFilter) return false
      if (search && !`${r.id} ${r.prefecture} ${r.city} ${r.address}`.includes(search)) return false
      const currentTags = titles.manholes[r.id]?.tags ?? []
      const hasLocationTag = LOCATION_TAGS.some(t => currentTags.includes(t))
      if (showFilter === 'has_tag' && !hasLocationTag) return false
      if (showFilter === 'no_tag' && hasLocationTag) return false
      return true
    })
  }, [records, titles, prefFilter, search, showFilter])

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
      // If same as base, remove from pending
      if ([...current].sort().join() === [...base].sort().join()) {
        next.delete(id)
      } else {
        next.set(id, current)
      }
      return next
    })
  }

  const pendingCount = pending.size

  async function handleSaveAll() {
    setSaveError(null)
    for (const [id, tags] of pending.entries()) {
      const base = new Set(titles.manholes[id]?.tags ?? [])
      const added = [...tags].filter(t => !base.has(t))
      const removed = [...base].filter(t => !tags.has(t))

      if (added.length > 0) {
        const patch: SemanticPatch = {
          id: newPatchId(),
          createdAt: new Date().toISOString(),
          taskType: 'assign_location_tags',
          operation: 'add_tags',
          target: 'manholes',
          manholeIds: [parseInt(id, 10)],
          payload: { tags: added },
        }
        const v = validatePatch(patch, titles)
        if (!v.valid) { setSaveError(v.errors.join('\n')); return }
        await onSave(patch)
      }
      if (removed.length > 0) {
        const patch: SemanticPatch = {
          id: newPatchId(),
          createdAt: new Date().toISOString(),
          taskType: 'assign_location_tags',
          operation: 'remove_tags',
          target: 'manholes',
          manholeIds: [parseInt(id, 10)],
          payload: { tags: removed },
        }
        await onSave(patch)
      }
    }
    setPending(new Map())
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>海・湖・離島タグを付ける</h2>
        {pendingCount > 0 && (
          <button
            className="btn btn-primary"
            onClick={handleSaveAll}
            disabled={saving}
          >
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
          style={{ width: 260 }}
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
        <span style={{ color: '#6b7280', fontSize: 13 }}>{filtered.length}件</span>
      </div>

      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 60 }}>ID</th>
            <th>場所</th>
            <th>住所</th>
            <th>地図</th>
            <th>タグ</th>
          </tr>
        </thead>
        <tbody>
          {filtered.slice(0, 200).map(r => {
            const effectiveTags = getEffectiveTags(r.id)
            const isDirty = pending.has(r.id)
            return (
              <tr key={r.id} style={isDirty ? { background: '#fefce8' } : undefined}>
                <td style={{ fontFamily: 'monospace' }}>{r.id}</td>
                <td>
                  <div>{r.prefecture} {r.city}</div>
                  {titles.manholes[r.id]?.building && (
                    <div style={{ fontSize: 11, color: '#6b7280' }}>{titles.manholes[r.id].building}</div>
                  )}
                </td>
                <td style={{ fontSize: 12, maxWidth: 200, wordBreak: 'break-all' }}>{r.address}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <a href={`https://maps.google.com/?q=${r.lat},${r.lng}`} target="_blank" rel="noreferrer" style={{ fontSize: 12, marginRight: 6 }}>GM</a>
                  <a href={`https://www.openstreetmap.org/?mlat=${r.lat}&mlon=${r.lng}&zoom=17`} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>OSM</a>
                </td>
                <td>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {LOCATION_TAGS.map(tag => (
                      <button
                        key={tag}
                        className={`tag ${effectiveTags.has(tag) ? 'tag-active' : 'tag-inactive'}`}
                        onClick={() => toggleTag(r.id, tag)}
                        title={tag}
                      >
                        {TAG_LABEL[tag]}
                      </button>
                    ))}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {filtered.length > 200 && (
        <p style={{ color: '#6b7280', fontSize: 13, marginTop: 8 }}>
          先頭200件を表示。絞り込みで件数を減らしてください。
        </p>
      )}
    </div>
  )
}
