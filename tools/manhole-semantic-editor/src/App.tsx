import { useState, useEffect, useCallback } from 'react'
import './styles.css'
import type { ManholeTitlesJson, PokefutaRecord, SemanticPatch, TaskType } from './semantic/semanticPatch'
import { loadPokefutaRecords } from './data/loadReadonlyNdjson'
import { loadTitles, loadSessionPatches, savePatch as savePatchToBackend, savePatches as savePatchesToBackend } from './data/loadSemanticJson'
import { AssignLocationTagsTask } from './tasks/assignLocationTags/AssignLocationTagsTask'
import { AddMunicipalityUrlTask } from './tasks/addMunicipalityUrl/AddMunicipalityUrlTask'
import { VerifyOfficialUrlTask } from './tasks/verifyOfficialUrl/VerifyOfficialUrlTask'
import { VerifyTitleTask } from './tasks/verifyTitle/VerifyTitleTask'
import { AssignStationTagsTask } from './tasks/assignStationTags/AssignStationTagsTask'
import { AdminBulkEditTask } from './tasks/adminBulkEdit/AdminBulkEditTask'

type ActiveTask = 'home' | TaskType

const TASK_MENU: Array<{ group: string; items: Array<{ id: TaskType; label: string; icon: string; desc: string; admin?: boolean }> }> = [
  {
    group: '通常作業',
    items: [
      { id: 'add_municipality_url', label: '自治体URLを追加する', icon: '🏛', desc: '市区町村の公式案内ページ' },
      { id: 'verify_official_url', label: '公式URLを確認する', icon: '🔗', desc: 'official_url フィールド' },
      { id: 'assign_location_tags', label: '海・湖・離島タグを付ける', icon: '🌊', desc: 'seaside / lakeside / remote_island' },
      { id: 'assign_station_tags', label: '駅近・駅構内タグを付ける', icon: '🚉', desc: 'in_station / near_station など' },
      { id: 'assign_tourism_tags', label: '観光地タグを付ける', icon: '🗺', desc: 'tourism / park / museum など' },
      { id: 'verify_title', label: 'titleを確認する', icon: '✏️', desc: 'confidence / verified_at' },
    ],
  },
  {
    group: 'Admin',
    items: [
      { id: 'admin_edit_manhole', label: '特定マンホール編集', icon: '🔧', desc: 'ID指定で直接編集', admin: true },
      { id: 'admin_bulk_edit', label: '一括編集', icon: '⚙️', desc: '複数件を条件で一括変更', admin: true },
    ],
  },
]

export default function App() {
  const [activeTask, setActiveTask] = useState<ActiveTask>('home')
  const [titles, setTitles] = useState<ManholeTitlesJson | null>(null)
  const [records, setRecords] = useState<PokefutaRecord[]>([])
  const [sessionPatches, setSessionPatches] = useState<SemanticPatch[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [prStatus, setPrStatus] = useState<string | null>(null)
  const [prRunning, setPrRunning] = useState(false)

  useEffect(() => {
    Promise.all([loadPokefutaRecords(), loadTitles(), loadSessionPatches()])
      .then(([recs, t, patches]) => {
        setRecords(recs)
        setTitles(t)
        setSessionPatches(patches)
      })
      .catch(e => setLoadError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  const handleSavePatch = useCallback(async (patch: SemanticPatch) => {
    if (!titles) return
    setSaving(true)
    try {
      const updated = await savePatchToBackend(patch, titles)
      setTitles(updated)
      setSessionPatches(prev => [...prev, patch])
    } finally {
      setSaving(false)
    }
  }, [titles])

  const handleSavePatches = useCallback(async (patches: SemanticPatch[]) => {
    if (!titles) return
    setSaving(true)
    try {
      const updated = await savePatchesToBackend(patches, titles)
      setTitles(updated)
      setSessionPatches(prev => [...prev, ...patches])
    } finally {
      setSaving(false)
    }
  }, [titles])

  async function handleCreatePR() {
    setPrRunning(true)
    setPrStatus(null)
    try {
      const res = await fetch('/__editor/pr/create', { method: 'POST' })
      const data = await res.json() as { ok: boolean; stdout?: string; error?: string }
      if (data.ok) {
        setPrStatus('✅ PR作成成功\n' + (data.stdout ?? ''))
        setSessionPatches([])
      } else {
        setPrStatus('❌ PR作成失敗\n' + (data.error ?? ''))
      }
    } catch (e) {
      setPrStatus('❌ ' + String(e))
    } finally {
      setPrRunning(false)
    }
  }

  const commonProps = { records, saving }

  function renderTask() {
    if (!titles) return null
    switch (activeTask) {
      case 'assign_location_tags':
        return <AssignLocationTagsTask {...commonProps} titles={titles} onSave={handleSavePatch} />
      case 'add_municipality_url':
        return <AddMunicipalityUrlTask {...commonProps} titles={titles} onSave={handleSavePatch} />
      case 'verify_official_url':
        return <VerifyOfficialUrlTask {...commonProps} titles={titles} onSave={handleSavePatch} />
      case 'verify_title':
        return <VerifyTitleTask {...commonProps} titles={titles} onSave={handleSavePatch} />
      case 'assign_station_tags':
        return <AssignStationTagsTask {...commonProps} titles={titles} onSave={handleSavePatch} />
      case 'assign_tourism_tags':
        return <AssignLocationTagsTask {...commonProps} titles={titles} onSave={handleSavePatch} />
      case 'admin_edit_manhole':
        return <AdminSingleEdit records={records} titles={titles} onSave={handleSavePatch} saving={saving} />
      case 'admin_bulk_edit':
        return <AdminBulkEditTask {...commonProps} titles={titles} onSaveMany={handleSavePatches} />
      default:
        return <Home onSelectTask={setActiveTask} />
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: '#6b7280' }}>
        データを読み込んでいます…
      </div>
    )
  }

  if (loadError) {
    return (
      <div style={{ padding: 40 }}>
        <div className="error-banner">
          <strong>データ読み込みエラー:</strong> {loadError}
          <br />
          <small>Vite dev server が起動していることを確認してください: npm run dev</small>
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>Semantic Editor</h1>
          <p>dataset/manhole_titles.json</p>
        </div>

        <ul className="task-menu">
          <li>
            <button className={activeTask === 'home' ? 'active' : ''} onClick={() => setActiveTask('home')}>
              🏠 ホーム
            </button>
          </li>
          {TASK_MENU.map(group => (
            <li key={group.group}>
              <div className="task-menu-group">{group.group}</div>
              <ul className="task-menu" style={{ padding: 0 }}>
                {group.items.map(item => (
                  <li key={item.id}>
                    <button
                      className={activeTask === item.id ? 'active' : ''}
                      onClick={() => setActiveTask(item.id)}
                    >
                      {item.icon} {item.label}
                    </button>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>

        <div className="sidebar-footer">
          <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 10 }}>
            このセッション: {sessionPatches.length}件の変更
            {sessionPatches.length > 0 && (
              <span className="badge">{sessionPatches.length}</span>
            )}
          </div>
          <button
            className="btn btn-primary btn-full"
            onClick={handleCreatePR}
            disabled={sessionPatches.length === 0 || prRunning}
          >
            {prRunning ? 'PR作成中…' : 'PR を作成する'}
          </button>
          {prStatus && (
            <pre style={{ marginTop: 10, fontSize: 11, color: prStatus.startsWith('✅') ? '#86efac' : '#fca5a5', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {prStatus}
            </pre>
          )}
        </div>
      </aside>

      <main className="main">
        {renderTask()}
      </main>
    </div>
  )
}

function Home({ onSelectTask }: { onSelectTask: (t: ActiveTask) => void }) {
  return (
    <div>
      <h2 style={{ marginBottom: 8 }}>Semantic Manhole Metadata Editor</h2>
      <p style={{ color: '#6b7280', marginBottom: 24 }}>
        ポケふたのセマンティックメタデータを安全に編集します。<br />
        <code>docs/pokefuta.ndjson</code> は読み取り専用 —
        <code>dataset/manhole_titles.json</code> のみ更新します。
      </p>
      <div className="home-grid">
        {TASK_MENU.flatMap(g => g.items).map(item => (
          <div
            key={item.id}
            className={`home-card${item.admin ? ' home-card-admin' : ''}`}
            onClick={() => onSelectTask(item.id)}
            role="button"
            tabIndex={0}
            onKeyDown={e => e.key === 'Enter' && onSelectTask(item.id)}
          >
            <div className="home-card-icon">{item.icon}</div>
            <div className="home-card-title">{item.label}</div>
            <div className="home-card-desc">{item.desc}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function AdminSingleEdit({
  records,
  titles,
  onSave,
  saving,
}: {
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSave: (p: SemanticPatch) => Promise<void>
  saving: boolean
}) {
  const [idInput, setIdInput] = useState('')
  const [tagInput, setTagInput] = useState('')
  const [official_url, setOfficialUrl] = useState('')
  const [building, setBuilding] = useState('')
  const [saved, setSaved] = useState(false)

  const record = records.find(r => r.id === idInput)
  const entry = titles.manholes[idInput]

  useEffect(() => {
    if (entry) {
      setTagInput((entry.tags ?? []).join(', '))
      setOfficialUrl(entry.official_url ?? '')
      setBuilding(entry.building ?? '')
    } else {
      setTagInput('')
      setOfficialUrl('')
      setBuilding('')
    }
    setSaved(false)
  }, [idInput, entry])

  async function handleSave() {
    if (!record) return
    const newTags = tagInput.split(',').map(t => t.trim()).filter(Boolean)
    const currentTags = entry?.tags ?? []
    const added = newTags.filter(t => !currentTags.includes(t))
    const removed = currentTags.filter(t => !newTags.includes(t))

    const id = parseInt(idInput, 10)
    const patches: SemanticPatch[] = []

    if (added.length > 0) {
      patches.push({ id: `${Date.now()}-a`, createdAt: new Date().toISOString(), taskType: 'admin_edit_manhole', operation: 'add_tags', target: 'manholes', manholeIds: [id], payload: { tags: added } })
    }
    if (removed.length > 0) {
      patches.push({ id: `${Date.now()}-r`, createdAt: new Date().toISOString(), taskType: 'admin_edit_manhole', operation: 'remove_tags', target: 'manholes', manholeIds: [id], payload: { tags: removed } })
    }
    if (official_url !== (entry?.official_url ?? '')) {
      patches.push({ id: `${Date.now()}-u`, createdAt: new Date().toISOString(), taskType: 'admin_edit_manhole', operation: 'set_official_url', target: 'manholes', manholeIds: [id], payload: { url: official_url } })
    }
    if (building !== (entry?.building ?? '')) {
      patches.push({ id: `${Date.now()}-b`, createdAt: new Date().toISOString(), taskType: 'admin_edit_manhole', operation: 'set_title', target: 'manholes', manholeIds: [id], payload: { building } })
    }

    for (const p of patches) await onSave(p)
    setSaved(true)
  }

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>Admin: 特定マンホール編集</h2>
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'flex-end' }}>
        <label>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>マンホール ID</div>
          <input
            type="number"
            value={idInput}
            onChange={e => setIdInput(e.target.value)}
            placeholder="例: 404"
            style={{ padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14, width: 120 }}
          />
        </label>
        {record && (
          <div style={{ fontSize: 13, color: '#6b7280' }}>
            {record.prefecture} {record.city} / {record.pokemons.join(', ')}
          </div>
        )}
        {idInput && !record && (
          <div style={{ fontSize: 13, color: '#dc2626' }}>ID が存在しません</div>
        )}
      </div>

      {record && (
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 20, maxWidth: 600 }}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>building</label>
            <input value={building} onChange={e => setBuilding(e.target.value)} style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }} />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>tags（カンマ区切り）</label>
            <input value={tagInput} onChange={e => setTagInput(e.target.value)} style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }} />
          </div>
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>official_url</label>
            <input type="url" value={official_url} onChange={e => setOfficialUrl(e.target.value)} style={{ width: '100%', padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13 }} />
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? '保存中…' : '保存'}
            </button>
            {saved && <span style={{ color: '#16a34a', fontSize: 13 }}>✓ 保存済み</span>}
          </div>
        </div>
      )}
    </div>
  )
}
