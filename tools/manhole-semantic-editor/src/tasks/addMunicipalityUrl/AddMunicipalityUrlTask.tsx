import { useState, useMemo } from 'react'
import type { PokefutaRecord, ManholeTitlesJson, SemanticPatch } from '../../semantic/semanticPatch'
import { normCity } from '../../data/loadSemanticJson'
import { validatePatch } from '../../semantic/semanticPatchValidator'
import { newPatchId } from '../../util'

type CityGroup = {
  prefecture: string
  city: string          // raw city from ndjson
  count: number
  ids: string[]
  hasLink: boolean
  existingUrl?: string
}

type Props = {
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSave: (patch: SemanticPatch) => Promise<void>
  saving: boolean
}

export function AddMunicipalityUrlTask({ records, titles, onSave, saving }: Props) {
  const [urlInputs, setUrlInputs] = useState<Record<string, string>>({})
  const [prefFilter, setPrefFilter] = useState('')
  const [showFilter, setShowFilter] = useState<'all' | 'missing' | 'has_link'>('missing')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set())

  const cityGroups = useMemo<CityGroup[]>(() => {
    const map = new Map<string, CityGroup>()
    for (const r of records) {
      if (r.status !== 'active') continue
      const key = `${r.prefecture}__${r.city}`
      if (!map.has(key)) {
        const existing = titles.city_links.find(
          cl =>
            cl.prefecture === r.prefecture &&
            normCity(cl.city) === normCity(r.city)
        )
        map.set(key, {
          prefecture: r.prefecture,
          city: r.city,
          count: 0,
          ids: [],
          hasLink: !!existing,
          existingUrl: existing?.url,
        })
      }
      const g = map.get(key)!
      g.count++
      g.ids.push(r.id)
    }
    return [...map.values()].sort((a, b) => {
      if (a.prefecture !== b.prefecture) return a.prefecture.localeCompare(b.prefecture)
      return a.city.localeCompare(b.city)
    })
  }, [records, titles])

  const prefectures = useMemo(
    () => [...new Set(cityGroups.map(g => g.prefecture))].sort(),
    [cityGroups]
  )

  const filtered = useMemo(() => {
    return cityGroups.filter(g => {
      if (prefFilter && g.prefecture !== prefFilter) return false
      if (showFilter === 'missing' && g.hasLink) return false
      if (showFilter === 'has_link' && !g.hasLink) return false
      return true
    })
  }, [cityGroups, prefFilter, showFilter])

  function groupKey(g: CityGroup) {
    return `${g.prefecture}__${g.city}`
  }

  async function handleSave(g: CityGroup) {
    const key = groupKey(g)
    const url = (urlInputs[key] ?? g.existingUrl ?? '').trim()
    if (!url) return
    setSaveError(null)

    const cityForLink = g.city + (g.city.match(/[市区町村郡]$/) ? '' : '市')
    const patch: SemanticPatch = {
      id: newPatchId(),
      createdAt: new Date().toISOString(),
      taskType: 'add_municipality_url',
      operation: 'set_municipality_url',
      target: 'city_links',
      payload: {},
      cityLinkEntry: { prefecture: g.prefecture, city: cityForLink, url },
    }
    const v = validatePatch(patch, titles)
    if (!v.valid) { setSaveError(v.errors.join('\n')); return }

    await onSave(patch)
    setSavedKeys(prev => new Set([...prev, key]))
    setUrlInputs(prev => { const n = { ...prev }; delete n[key]; return n })
  }

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>自治体URLを追加する</h2>
      <p style={{ color: '#6b7280', fontSize: 13, marginBottom: 16 }}>
        各自治体の公式ポケふた案内ページURLを <code>city_links</code> に登録します。
      </p>

      {saveError && (
        <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 6, padding: 12, marginBottom: 12, color: '#dc2626' }}>
          {saveError}
        </div>
      )}

      <div className="filter-bar">
        <select value={prefFilter} onChange={e => setPrefFilter(e.target.value)}>
          <option value="">全都道府県</option>
          {prefectures.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={showFilter} onChange={e => setShowFilter(e.target.value as typeof showFilter)}>
          <option value="missing">URLなし</option>
          <option value="has_link">登録済み</option>
          <option value="all">全件</option>
        </select>
        <span style={{ color: '#6b7280', fontSize: 13 }}>{filtered.length}件</span>
      </div>

      <table className="table">
        <thead>
          <tr>
            <th>都道府県</th>
            <th>市区町村</th>
            <th style={{ width: 60 }}>件数</th>
            <th>公式URL</th>
            <th style={{ width: 80 }}></th>
          </tr>
        </thead>
        <tbody>
          {filtered.map(g => {
            const key = groupKey(g)
            const isSaved = savedKeys.has(key)
            const inputVal = urlInputs[key] ?? g.existingUrl ?? ''
            return (
              <tr key={key} style={isSaved ? { background: '#f0fdf4' } : undefined}>
                <td>{g.prefecture}</td>
                <td>{g.city}</td>
                <td>{g.count}</td>
                <td>
                  {g.hasLink && !isSaved ? (
                    <span style={{ fontSize: 12, color: '#16a34a' }}>✓ {g.existingUrl}</span>
                  ) : (
                    <input
                      type="url"
                      value={inputVal}
                      onChange={e => setUrlInputs(prev => ({ ...prev, [key]: e.target.value }))}
                      placeholder="https://..."
                      style={{ width: '100%', padding: '4px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }}
                    />
                  )}
                </td>
                <td>
                  {isSaved ? (
                    <span style={{ color: '#16a34a', fontSize: 13 }}>保存済み</span>
                  ) : (
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleSave(g)}
                      disabled={saving || !inputVal.trim()}
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
    </div>
  )
}
