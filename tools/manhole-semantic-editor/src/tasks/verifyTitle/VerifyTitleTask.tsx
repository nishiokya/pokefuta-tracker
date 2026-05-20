import { useState, useMemo } from 'react'
import type { PokefutaRecord, ManholeTitlesJson, SemanticPatch, ConfidenceLevel } from '../../semantic/semanticPatch'
import { newPatchId, todayJST } from '../../util'

const CONF_LABELS: Record<number, string> = { 1: '低 (1)', 2: '中 (2)', 3: '高 (3)', 4: '確認済 (4)' }
const CONF_LEVEL_MAP: Record<number, ConfidenceLevel> = { 1: 'low', 2: 'medium', 3: 'high', 4: 'verified' }

type Props = {
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSave: (patch: SemanticPatch) => Promise<void>
  saving: boolean
}

export function VerifyTitleTask({ records, titles, onSave, saving }: Props) {
  const [search, setSearch] = useState('')
  const [prefFilter, setPrefFilter] = useState('')
  const [showFilter, setShowFilter] = useState<'has_building' | 'all' | 'unverified'>('has_building')
  const [confInputs, setConfInputs] = useState<Record<string, number>>({})
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
      if (showFilter === 'has_building' && !entry?.building) return false
      if (showFilter === 'unverified' && entry?.confidence === 4) return false
      return true
    })
  }, [records, titles, prefFilter, search, showFilter])

  async function handleSave(r: PokefutaRecord) {
    const entry = titles.manholes[r.id]
    const confNum = confInputs[r.id] ?? entry?.confidence ?? 2
    setSaveError(null)
    const patch: SemanticPatch = {
      id: newPatchId(),
      createdAt: new Date().toISOString(),
      taskType: 'verify_title',
      operation: 'set_confidence',
      target: 'manholes',
      manholeIds: [parseInt(r.id, 10)],
      payload: { verified_at: todayJST() },
      confidence: CONF_LEVEL_MAP[confNum],
    }
    try {
      await onSave(patch)
      setSavedIds(prev => new Set([...prev, r.id]))
    } catch (e) {
      setSaveError(String(e))
    }
  }

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>titleを確認する</h2>
      <p style={{ color: '#6b7280', fontSize: 13, marginBottom: 16 }}>
        building・住所情報の信頼度（confidence）を確認・更新します。
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
          <option value="unverified">未確認（confidence &lt; 4）</option>
          <option value="all">全件</option>
        </select>
        <span style={{ color: '#6b7280', fontSize: 13 }}>{filtered.length}件</span>
      </div>

      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 55 }}>ID</th>
            <th>ndjson title</th>
            <th>building / place</th>
            <th>住所</th>
            <th>confidence</th>
            <th style={{ width: 80 }}></th>
          </tr>
        </thead>
        <tbody>
          {filtered.slice(0, 200).map(r => {
            const entry = titles.manholes[r.id]
            const isSaved = savedIds.has(r.id)
            const currentConf = entry?.confidence ?? 1
            const inputConf = confInputs[r.id] ?? currentConf
            return (
              <tr key={r.id} style={isSaved ? { background: '#f0fdf4' } : undefined}>
                <td style={{ fontFamily: 'monospace' }}>{r.id}</td>
                <td style={{ fontSize: 12 }}>
                  <div>{r.title}</div>
                  <div style={{ color: '#6b7280' }}>{r.pokemons.join(', ')}</div>
                </td>
                <td style={{ fontSize: 12 }}>
                  {entry?.building && <div>{entry.building}</div>}
                  {entry?.place_detail && <div style={{ color: '#6b7280' }}>{entry.place_detail}</div>}
                  {!entry?.building && <span style={{ color: '#d1d5db' }}>—</span>}
                </td>
                <td style={{ fontSize: 11, color: '#6b7280', maxWidth: 160, wordBreak: 'break-all' }}>
                  {entry?.address_norm ?? r.address}
                </td>
                <td>
                  <select
                    value={inputConf}
                    onChange={e => setConfInputs(prev => ({ ...prev, [r.id]: parseInt(e.target.value, 10) }))}
                    style={{ padding: '4px 6px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 12 }}
                  >
                    {[1, 2, 3, 4].map(n => (
                      <option key={n} value={n}>{CONF_LABELS[n]}</option>
                    ))}
                  </select>
                  {entry?.verified_at && (
                    <div style={{ fontSize: 10, color: '#6b7280', marginTop: 2 }}>{entry.verified_at}</div>
                  )}
                </td>
                <td>
                  {isSaved ? (
                    <span style={{ color: '#16a34a', fontSize: 12 }}>保存済み</span>
                  ) : (
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleSave(r)}
                      disabled={saving || (inputConf === currentConf && !!entry?.verified_at)}
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
