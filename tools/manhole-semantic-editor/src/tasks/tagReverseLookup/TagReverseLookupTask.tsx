import { useState, useMemo } from 'react'
import type { ManholeTitlesJson, PokefutaRecord } from '../../semantic/semanticPatch'
import { VALID_TAGS } from '../../semantic/validTags'

type Props = {
  titles: ManholeTitlesJson
  records: PokefutaRecord[]
  onNavigateToEdit: (manholeId: string) => void
}

type TagRow = {
  key: string
  emoji: string
  label: string
  priority: number
  count: number
  editable: boolean  // VALID_TAGS に含まれる手動タグか否か
}

type ManholeItem = {
  id: string
  record: PokefutaRecord | undefined
  // manual tag のとき entry.tags から来る; auto title のとき record.titles から来る
  badgeLabel?: string
}

export function TagReverseLookupTask({ titles, records, onNavigateToEdit }: Props) {
  const [selectedTag, setSelectedTag] = useState<string | null>(null)

  const editableKeys = useMemo(() => new Set<string>(VALID_TAGS), [])

  const recordById = useMemo(() => {
    const map = new Map<string, PokefutaRecord>()
    for (const r of records) map.set(r.id, r)
    return map
  }, [records])

  // 自動称号キーごとに manhole ID リストを構築（records[].titles から）
  const autoTagToIds = useMemo(() => {
    const result = new Map<string, string[]>()
    for (const r of records) {
      for (const t of r.titles ?? []) {
        if (!editableKeys.has(t.key)) {
          if (!result.has(t.key)) result.set(t.key, [])
          result.get(t.key)!.push(r.id)
        }
      }
    }
    return result
  }, [records, editableKeys])

  // 手動タグキーごとに manhole ID リストを構築（manholes[].tags から）
  const manualTagToIds = useMemo(() => {
    const result = new Map<string, string[]>()
    for (const tag of VALID_TAGS) result.set(tag, [])
    for (const [id, entry] of Object.entries(titles.manholes)) {
      for (const tag of entry.tags ?? []) {
        const list = result.get(tag)
        if (list) list.push(id)
      }
    }
    return result
  }, [titles])

  // 全 vocabulary を TagRow に変換
  const tagRows = useMemo((): TagRow[] => {
    const vocab = titles.vocabulary
    return Object.entries(vocab)
      .map(([key, v]): TagRow => {
        const editable = editableKeys.has(key)
        const count = editable
          ? (manualTagToIds.get(key)?.length ?? 0)
          : (autoTagToIds.get(key)?.length ?? 0)
        return {
          key,
          emoji: v.emoji ?? '',
          label: v.label ?? key,
          priority: v.priority ?? 0,
          count,
          editable,
        }
      })
      .sort((a, b) => b.priority - a.priority || b.count - a.count)
  }, [titles, editableKeys, manualTagToIds, autoTagToIds])

  const manholeList = useMemo((): ManholeItem[] => {
    if (!selectedTag) return []
    const isEditable = editableKeys.has(selectedTag)
    if (isEditable) {
      return (manualTagToIds.get(selectedTag) ?? [])
        .map(id => ({ id, record: recordById.get(id) }))
        .sort((a, b) => Number(a.id) - Number(b.id))
    } else {
      return (autoTagToIds.get(selectedTag) ?? [])
        .map(id => {
          const r = recordById.get(id)
          const badge = r?.titles?.find(t => t.key === selectedTag)
          return { id, record: r, badgeLabel: badge?.label }
        })
        .sort((a, b) => Number(a.id) - Number(b.id))
    }
  }, [selectedTag, editableKeys, manualTagToIds, autoTagToIds, recordById])

  const selectedRow = useMemo(
    () => tagRows.find(r => r.key === selectedTag),
    [tagRows, selectedTag]
  )

  return (
    <div style={{ display: 'flex', gap: 0, height: '100%' }}>
      {/* 左ペイン: タグ一覧 */}
      <div style={{ width: 380, flexShrink: 0, borderRight: '1px solid #e2e8f0', overflowY: 'auto', padding: '16px 12px' }}>
        <h2 style={{ fontSize: 16, marginBottom: 4 }}>タグ / 称号 一覧</h2>
        <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
          クリックするとそのタグ・称号が付いたマンホールを表示します。<br />
          <span style={{ color: '#7c3aed' }}>●</span> 手動タグ（編集可）　<span style={{ color: '#94a3b8' }}>●</span> 自動計算称号（読み取り専用）
        </p>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
              <th style={{ padding: '4px 4px', color: '#6b7280', fontWeight: 600, textAlign: 'left', width: 8 }}></th>
              <th style={{ padding: '4px 6px', color: '#6b7280', fontWeight: 600, textAlign: 'left' }}>キー</th>
              <th style={{ padding: '4px 6px', color: '#6b7280', fontWeight: 600, textAlign: 'left' }}>ラベル</th>
              <th style={{ padding: '4px 6px', color: '#6b7280', fontWeight: 600, textAlign: 'right', width: 40 }}>件数</th>
            </tr>
          </thead>
          <tbody>
            {tagRows.map(row => {
              const isActive = selectedTag === row.key
              return (
                <tr
                  key={row.key}
                  onClick={() => setSelectedTag(isActive ? null : row.key)}
                  style={{
                    borderBottom: '1px solid #f1f5f9',
                    background: isActive ? '#7c5cbf' : row.count === 0 ? '#f9fafb' : '#fff',
                    color: isActive ? '#fff' : row.count === 0 ? '#9ca3af' : '#1e293b',
                    cursor: 'pointer',
                  }}
                >
                  <td style={{ padding: '5px 4px', textAlign: 'center' }}>
                    <span style={{
                      display: 'inline-block',
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: row.editable
                        ? (isActive ? '#c4b5d4' : '#7c3aed')
                        : (isActive ? '#c4b5d4' : '#94a3b8'),
                    }} />
                  </td>
                  <td style={{ padding: '5px 6px', fontFamily: 'monospace', fontSize: 11, whiteSpace: 'nowrap' }}>
                    {row.key}
                  </td>
                  <td style={{ padding: '5px 6px' }}>
                    {row.emoji} {row.label.replace(/\{[^}]+\}/g, '…')}
                  </td>
                  <td style={{
                    padding: '5px 6px',
                    textAlign: 'right',
                    fontWeight: 700,
                    color: isActive ? '#fff' : row.count === 0 ? '#9ca3af' : '#7c3aed',
                  }}>
                    {row.count}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* 右ペイン: マンホール一覧 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
        {!selectedTag ? (
          <div style={{ color: '#6b7280', marginTop: 40, textAlign: 'center' }}>
            ← タグ / 称号を選択するとマンホール一覧が表示されます
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <h3 style={{ margin: 0, fontSize: 15 }}>
                {selectedRow?.emoji} {selectedRow?.label.replace(/\{[^}]+\}/g, '…')}
              </h3>
              <code style={{ fontSize: 11, color: '#64748b', background: '#f1f5f9', padding: '2px 6px', borderRadius: 4 }}>{selectedTag}</code>
              <span style={{ fontSize: 13, color: '#6b7280' }}>{manholeList.length}件</span>
              {!editableKeys.has(selectedTag) && (
                <span style={{ fontSize: 11, color: '#94a3b8', background: '#f1f5f9', padding: '2px 8px', borderRadius: 4 }}>自動計算・読み取り専用</span>
              )}
            </div>
            {manholeList.length === 0 ? (
              <p style={{ color: '#9ca3af' }}>このタグ / 称号が付いているマンホールはありません。</p>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #e2e8f0', textAlign: 'left' }}>
                    <th style={{ padding: '6px 8px', color: '#6b7280', fontWeight: 600, width: 55 }}>ID</th>
                    <th style={{ padding: '6px 8px', color: '#6b7280', fontWeight: 600 }}>タイトル</th>
                    <th style={{ padding: '6px 8px', color: '#6b7280', fontWeight: 600 }}>都道府県</th>
                    <th style={{ padding: '6px 8px', color: '#6b7280', fontWeight: 600 }}>市区町村</th>
                    {!editableKeys.has(selectedTag) && (
                      <th style={{ padding: '6px 8px', color: '#6b7280', fontWeight: 600 }}>称号ラベル</th>
                    )}
                    {editableKeys.has(selectedTag) && (
                      <th style={{ padding: '6px 8px', width: 100 }}></th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {manholeList.map(({ id, record, badgeLabel }) => (
                    <tr key={id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '6px 8px', color: '#64748b', fontVariantNumeric: 'tabular-nums' }}>{id}</td>
                      <td style={{ padding: '6px 8px' }}>
                        {record?.title ?? titles.manholes[id]?.building ?? '—'}
                      </td>
                      <td style={{ padding: '6px 8px', color: '#64748b' }}>
                        {record?.prefecture ?? titles.manholes[id]?.prefecture ?? '—'}
                      </td>
                      <td style={{ padding: '6px 8px', color: '#64748b' }}>
                        {record?.city ?? titles.manholes[id]?.city ?? '—'}
                      </td>
                      {!editableKeys.has(selectedTag) && (
                        <td style={{ padding: '6px 8px', color: '#64748b', fontSize: 12 }}>
                          {badgeLabel ?? '—'}
                        </td>
                      )}
                      {editableKeys.has(selectedTag) && (
                        <td style={{ padding: '6px 8px' }}>
                          <button
                            onClick={() => onNavigateToEdit(id)}
                            style={{
                              padding: '4px 10px',
                              fontSize: 12,
                              borderRadius: 6,
                              border: '1px solid #c4b5d4',
                              background: '#f8f4ff',
                              color: '#7c3aed',
                              cursor: 'pointer',
                            }}
                          >
                            タグを編集
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </div>
  )
}
