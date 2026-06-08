import { useState, useMemo } from 'react'
import type { ManholeTitlesJson, PokefutaRecord } from '../../semantic/semanticPatch'
import { VALID_TAGS } from '../../semantic/validTags'
import { TagDetailView } from './TagDetailView'
import type { TagRow, ManholeItem } from './TagDetailView'

type Props = {
  titles: ManholeTitlesJson
  records: PokefutaRecord[]
  onNavigateToEdit: (manholeId: string) => void
}

export function TagReverseLookupTask({ titles, records, onNavigateToEdit }: Props) {
  const [detailTag, setDetailTag] = useState<string | null>(null)

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

  // 全 vocabulary を TagRow に変換 — 件数降順、同数は priority 降順
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
      .sort((a, b) => b.count - a.count || b.priority - a.priority)
  }, [titles, editableKeys, manualTagToIds, autoTagToIds])

  const detailManholes = useMemo((): ManholeItem[] => {
    if (!detailTag) return []
    const isEditable = editableKeys.has(detailTag)
    if (isEditable) {
      return (manualTagToIds.get(detailTag) ?? [])
        .map(id => ({ id, record: recordById.get(id) }))
        .sort((a, b) => Number(a.id) - Number(b.id))
    } else {
      return (autoTagToIds.get(detailTag) ?? [])
        .map(id => {
          const r = recordById.get(id)
          const badge = r?.titles?.find(t => t.key === detailTag)
          return { id, record: r, badgeLabel: badge?.label }
        })
        .sort((a, b) => Number(a.id) - Number(b.id))
    }
  }, [detailTag, editableKeys, manualTagToIds, autoTagToIds, recordById])

  const detailRow = useMemo(
    () => tagRows.find(r => r.key === detailTag) ?? null,
    [tagRows, detailTag]
  )

  // タグ詳細ページ
  if (detailTag && detailRow) {
    return (
      <TagDetailView
        tagRow={detailRow}
        manholeList={detailManholes}
        editable={editableKeys.has(detailTag)}
        onBack={() => setDetailTag(null)}
        onNavigateToEdit={onNavigateToEdit}
      />
    )
  }

  // タグ一覧ページ
  return (
    <div>
      <h2 style={{ fontSize: 18, marginBottom: 6 }}>タグ / 称号 一覧</h2>
      <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
        クリックするとそのタグ・称号が付いたマンホールを地図で確認できます。<br />
        <span style={{ color: '#7c3aed' }}>●</span> 手動タグ（編集可）　<span style={{ color: '#94a3b8' }}>●</span> 自動計算称号（読み取り専用）
      </p>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
            <th style={{ padding: '6px 6px', color: '#6b7280', fontWeight: 600, textAlign: 'left', width: 12 }}></th>
            <th style={{ padding: '6px 8px', color: '#6b7280', fontWeight: 600, textAlign: 'left' }}>キー</th>
            <th style={{ padding: '6px 8px', color: '#6b7280', fontWeight: 600, textAlign: 'left' }}>ラベル</th>
            <th style={{ padding: '6px 8px', color: '#6b7280', fontWeight: 600, textAlign: 'right', width: 60 }}>件数</th>
          </tr>
        </thead>
        <tbody>
          {tagRows.map(row => (
            <tr
              key={row.key}
              onClick={() => setDetailTag(row.key)}
              style={{
                borderBottom: '1px solid #f1f5f9',
                background: row.count === 0 ? '#f9fafb' : '#fff',
                color: row.count === 0 ? '#9ca3af' : '#1e293b',
                cursor: 'pointer',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLTableRowElement).style.background = '#f0f4ff' }}
              onMouseLeave={e => { (e.currentTarget as HTMLTableRowElement).style.background = row.count === 0 ? '#f9fafb' : '#fff' }}
            >
              <td style={{ padding: '8px 6px', textAlign: 'center' }}>
                <span style={{
                  display: 'inline-block',
                  width: 9,
                  height: 9,
                  borderRadius: '50%',
                  background: row.editable ? '#7c3aed' : '#94a3b8',
                }} />
              </td>
              <td style={{ padding: '8px 8px', fontFamily: 'monospace', fontSize: 12, whiteSpace: 'nowrap', color: '#64748b' }}>
                {row.key}
              </td>
              <td style={{ padding: '8px 8px', fontSize: 15 }}>
                {row.emoji} {row.label.replace(/\{[^}]+\}/g, '…')}
              </td>
              <td style={{
                padding: '8px 8px',
                textAlign: 'right',
                fontWeight: 700,
                fontSize: 16,
                color: row.count === 0 ? '#9ca3af' : '#7c3aed',
              }}>
                {row.count}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
