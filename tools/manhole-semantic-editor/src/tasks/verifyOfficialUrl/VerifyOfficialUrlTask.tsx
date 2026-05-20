import { useState, useMemo } from 'react'
import type { PokefutaRecord, ManholeTitlesJson, SemanticPatch } from '../../semantic/semanticPatch'
import { newPatchId } from '../../util'

type Props = {
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSave: (patch: SemanticPatch) => Promise<void>
  saving: boolean
}

export function VerifyOfficialUrlTask({ records, titles, onSave, saving }: Props) {
  const [search, setSearch] = useState('')
  const [prefFilter, setPrefFilter] = useState('')
  const [showFilter, setShowFilter] = useState<'all' | 'has_url' | 'no_url' | 'has_building'>('has_building')
  const [urlInputs, setUrlInputs] = useState<Record<string, string>>({})
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())
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
      const entry = titles.manholes[r.id]
      const hasUrl = !!entry?.official_url
      const hasBuilding = !!entry?.building
      if (showFilter === 'has_url' && !hasUrl) return false
      if (showFilter === 'no_url' && hasUrl) return false
      if (showFilter === 'has_building' && !hasBuilding) return false
      return true
    })
  }, [records, titles, prefFilter, search, showFilter])

  async function handleSave(r: PokefutaRecord) {
    const url = (urlInputs[r.id] ?? titles.manholes[r.id]?.official_url ?? '').trim()
    setSaveError(null)
    const patch: SemanticPatch = {
      id: newPatchId(),
      createdAt: new Date().toISOString(),
      taskType: 'verify_official_url',
      operation: 'set_official_url',
      target: 'manholes',
      manholeIds: [parseInt(r.id, 10)],
      payload: { url },
    }
    try {
      await onSave(patch)
      setSavedIds(prev => new Set([...prev, r.id]))
      setUrlInputs(prev => { const n = { ...prev }; delete n[r.id]; return n })
    } catch (e) {
      setSaveError(String(e))
    }
  }

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>公式URLを確認する</h2>
      <p style={{ color: '#6b7280', fontSize: 13, marginBottom: 16 }}>
        各マンホールの公式情報ページや設置案内URLを <code>official_url</code> に登録します。
      </p>

      {saveError && (
        <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 6, padding: 12, marginBottom: 12, color: '#dc2626' }}>
          {saveError}
        </div>
      )}

      <div className="filter-bar">
        <input
          placeholder="ID / 住所で絞り込み"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 220 }}
        />
        <select value={prefFilter} onChange={e => setPrefFilter(e.target.value)}>
          <option value="">全都道府県</option>
          {prefectures.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={showFilter} onChange={e => setShowFilter(e.target.value as typeof showFilter)}>
          <option value="has_building">building登録済み</option>
          <option value="no_url">official_urlなし</option>
          <option value="has_url">official_urlあり</option>
          <option value="all">全件</option>
        </select>
        <span style={{ color: '#6b7280', fontSize: 13 }}>{filtered.length}件</span>
      </div>

      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 55 }}>ID</th>
            <th>場所</th>
            <th>公式URL (ndjson detail_url)</th>
            <th>official_url</th>
            <th style={{ width: 80 }}></th>
          </tr>
        </thead>
        <tbody>
          {filtered.slice(0, 200).map(r => {
            const entry = titles.manholes[r.id]
            const isSaved = savedIds.has(r.id)
            const currentUrl = entry?.official_url ?? ''
            const inputVal = urlInputs[r.id] ?? currentUrl
            return (
              <tr key={r.id} style={isSaved ? { background: '#f0fdf4' } : undefined}>
                <td style={{ fontFamily: 'monospace' }}>{r.id}</td>
                <td>
                  <div>{r.prefecture} {r.city}</div>
                  {entry?.building && (
                    <div style={{ fontSize: 11, color: '#374151' }}>{entry.building}</div>
                  )}
                  <div style={{ fontSize: 11, color: '#6b7280' }}>{r.address}</div>
                </td>
                <td style={{ fontSize: 12 }}>
                  <a href={r.detail_url} target="_blank" rel="noreferrer">{r.detail_url}</a>
                </td>
                <td>
                  <input
                    type="url"
                    value={inputVal}
                    onChange={e => setUrlInputs(prev => ({ ...prev, [r.id]: e.target.value }))}
                    placeholder="https://..."
                    style={{ width: '100%', padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 12 }}
                  />
                </td>
                <td>
                  {isSaved ? (
                    <span style={{ color: '#16a34a', fontSize: 12 }}>保存済み</span>
                  ) : (
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleSave(r)}
                      disabled={saving || inputVal === currentUrl}
                    >
                      保存
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {filtered.length > 200 && (
        <p style={{ color: '#6b7280', fontSize: 13, marginTop: 8 }}>先頭200件を表示。</p>
      )}
    </div>
  )
}
