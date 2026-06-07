import { useState, useMemo } from 'react'
import type { PokefutaRecord, ManholeTitlesJson, SemanticPatch, OperationType } from '../../semantic/semanticPatch'
import { generateConfirmationText } from '../../semantic/semanticPatchApplier'
import { newPatchId } from '../../util'
import { VALID_TAGS } from '../../semantic/validTags'

type Props = {
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSaveMany: (patches: SemanticPatch[]) => Promise<void>
  saving: boolean
}

export function AdminBulkEditTask({ records, titles, onSaveMany, saving }: Props) {
  const [operation, setOperation] = useState<OperationType>('add_tags')
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [prefFilter, setPrefFilter] = useState('')
  const [cityFilter, setCityFilter] = useState('')
  const [hasTagFilter, setHasTagFilter] = useState('')
  const [noTagFilter, setNoTagFilter] = useState('')
  const [idMin, setIdMin] = useState('')
  const [idMax, setIdMax] = useState('')
  const [previewed, setPreviewed] = useState(false)
  const [confirmInput, setConfirmInput] = useState('')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)

  const prefectures = useMemo(
    () => [...new Set(records.map(r => r.prefecture))].sort(),
    [records]
  )

  const affectedRecords = useMemo(() => {
    if (!previewed) return []
    return records.filter(r => {
      if (r.status !== 'active') return false
      if (prefFilter && r.prefecture !== prefFilter) return false
      if (cityFilter && !r.city.includes(cityFilter)) return false
      const tags = titles.manholes[r.id]?.tags ?? []
      if (hasTagFilter && !tags.includes(hasTagFilter)) return false
      if (noTagFilter && tags.includes(noTagFilter)) return false
      const id = parseInt(r.id, 10)
      if (idMin && id < parseInt(idMin, 10)) return false
      if (idMax && id > parseInt(idMax, 10)) return false
      return true
    })
  }, [previewed, records, titles, prefFilter, cityFilter, hasTagFilter, noTagFilter, idMin, idMax])

  const draftPatch = useMemo((): SemanticPatch | null => {
    if (!affectedRecords.length || !selectedTags.length) return null
    return {
      id: newPatchId(),
      createdAt: new Date().toISOString(),
      taskType: 'admin_bulk_edit',
      operation,
      target: 'manholes',
      manholeIds: affectedRecords.map(r => parseInt(r.id, 10)),
      payload: { tags: selectedTags },
    }
  }, [affectedRecords, operation, selectedTags])

  const confirmationText = draftPatch ? generateConfirmationText(draftPatch) : ''
  const canSave = draftPatch && confirmInput.trim() === confirmationText && !saving

  function addTag(tag: string) {
    const t = tag.trim()
    if (t && !selectedTags.includes(t)) setSelectedTags(prev => [...prev, t])
    setTagInput('')
  }

  function removeTag(tag: string) {
    setSelectedTags(prev => prev.filter(t => t !== tag))
  }

  async function handleSave() {
    if (!draftPatch) return
    setSaveError(null)
    try {
      await onSaveMany([draftPatch])
      setSaveSuccess(true)
      setPreviewed(false)
      setConfirmInput('')
    } catch (e) {
      setSaveError(String(e))
    }
  }

  function previewTags(r: PokefutaRecord): { current: string[]; next: string[] } {
    const current = [...(titles.manholes[r.id]?.tags ?? [])]
    let next = current
    if (operation === 'add_tags') {
      next = [...new Set([...current, ...selectedTags])]
    } else if (operation === 'remove_tags') {
      next = current.filter(t => !selectedTags.includes(t))
    }
    return { current, next }
  }

  return (
    <div>
      <h2 style={{ marginBottom: 4 }}>Admin: 一括編集</h2>
      <p style={{ color: '#dc2626', fontSize: 13, marginBottom: 20 }}>
        ⚠️ 管理者専用。操作前にドライランで対象を確認してください。
      </p>

      {saveSuccess && (
        <div style={{ background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 6, padding: 12, marginBottom: 16, color: '#15803d' }}>
          保存が完了しました。
        </div>
      )}
      {saveError && (
        <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 6, padding: 12, marginBottom: 16, color: '#dc2626' }}>
          {saveError}
        </div>
      )}

      <section style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 20, marginBottom: 20 }}>
        <h3 style={{ marginBottom: 12, fontSize: 15 }}>1. 操作を選択</h3>
        <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
          {(['add_tags', 'remove_tags'] as OperationType[]).map(op => (
            <label key={op} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input
                type="radio"
                name="operation"
                value={op}
                checked={operation === op}
                onChange={() => { setOperation(op); setPreviewed(false); setSaveSuccess(false) }}
              />
              {op === 'add_tags' ? 'タグを追加' : 'タグを削除'}
            </label>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            value={tagInput}
            onChange={e => { setTagInput(e.target.value); if (e.target.value) addTag(e.target.value) }}
            style={{ padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }}
          >
            <option value="">タグを選択…</option>
            {VALID_TAGS.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          {selectedTags.map(t => (
            <span key={t} className="tag tag-active" style={{ cursor: 'pointer' }} onClick={() => removeTag(t)}>
              {t} ×
            </span>
          ))}
        </div>
      </section>

      <section style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 20, marginBottom: 20 }}>
        <h3 style={{ marginBottom: 12, fontSize: 15 }}>2. 対象を絞り込む</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <label>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>都道府県</div>
            <select value={prefFilter} onChange={e => setPrefFilter(e.target.value)} style={{ width: '100%', padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }}>
              <option value="">全て</option>
              {prefectures.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>市区町村 (部分一致)</div>
            <input value={cityFilter} onChange={e => setCityFilter(e.target.value)} placeholder="例: 指宿" style={{ width: '100%', padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }} />
          </label>
          <label>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>このタグを持つ</div>
            <select value={hasTagFilter} onChange={e => setHasTagFilter(e.target.value)} style={{ width: '100%', padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }}>
              <option value="">指定なし</option>
              {VALID_TAGS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>このタグを持たない</div>
            <select value={noTagFilter} onChange={e => setNoTagFilter(e.target.value)} style={{ width: '100%', padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }}>
              <option value="">指定なし</option>
              {VALID_TAGS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>ID min</div>
            <input type="number" value={idMin} onChange={e => setIdMin(e.target.value)} style={{ width: '100%', padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }} />
          </label>
          <label>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>ID max</div>
            <input type="number" value={idMax} onChange={e => setIdMax(e.target.value)} style={{ width: '100%', padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }} />
          </label>
        </div>

        <button
          className="btn btn-primary"
          style={{ marginTop: 16 }}
          onClick={() => { setPreviewed(true); setSaveSuccess(false); setConfirmInput('') }}
          disabled={selectedTags.length === 0}
        >
          ドライランで確認
        </button>
      </section>

      {previewed && (
        <section style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 20, marginBottom: 20 }}>
          <h3 style={{ marginBottom: 12, fontSize: 15 }}>3. 対象プレビュー（{affectedRecords.length}件）</h3>
          {affectedRecords.length === 0 ? (
            <p style={{ color: '#6b7280' }}>条件に一致するレコードがありません。</p>
          ) : (
            <>
              <div style={{ maxHeight: 300, overflowY: 'auto', marginBottom: 16 }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: 55 }}>ID</th>
                      <th>場所</th>
                      <th>現在のタグ</th>
                      <th>変更後のタグ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {affectedRecords.slice(0, 100).map(r => {
                      const { current, next } = previewTags(r)
                      return (
                        <tr key={r.id}>
                          <td style={{ fontFamily: 'monospace' }}>{r.id}</td>
                          <td style={{ fontSize: 12 }}>{r.prefecture} {r.city}</td>
                          <td style={{ fontSize: 12 }}>{current.join(', ') || '—'}</td>
                          <td style={{ fontSize: 12, color: '#2563eb' }}>{next.join(', ') || '—'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {draftPatch && (
                <div className="confirmation-box">
                  <p style={{ fontSize: 14, marginBottom: 8 }}>保存するには、以下のテキストを正確に入力してください：</p>
                  <div className="confirmation-code">{confirmationText}</div>
                  <input
                    type="text"
                    value={confirmInput}
                    onChange={e => setConfirmInput(e.target.value)}
                    placeholder="上記テキストを入力…"
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      border: `2px solid ${confirmInput === confirmationText ? '#22c55e' : '#d1d5db'}`,
                      borderRadius: 4,
                      fontFamily: 'monospace',
                      fontSize: 14,
                    }}
                  />
                  <button
                    className="btn btn-danger"
                    style={{ marginTop: 12 }}
                    onClick={handleSave}
                    disabled={!canSave}
                  >
                    {saving ? '保存中…' : `${affectedRecords.length}件を一括更新`}
                  </button>
                </div>
              )}
            </>
          )}
        </section>
      )}
    </div>
  )
}
