import { useState, useEffect, useCallback } from 'react'
import './styles.css'
import type { ManholeTitlesJson, PokefutaRecord, SemanticPatch, TaskType } from './semantic/semanticPatch'
import { loadPokefutaRecords } from './data/loadReadonlyNdjson'
import { loadTitles, loadSessionPatches, savePatch as savePatchToBackend, savePatches as savePatchesToBackend } from './data/loadSemanticJson'
import { AddMunicipalityUrlTask } from './tasks/addMunicipalityUrl/AddMunicipalityUrlTask'
import { VerifyOfficialUrlTask } from './tasks/verifyOfficialUrl/VerifyOfficialUrlTask'
import { AssignAllTagsTask } from './tasks/assignAllTags/AssignAllTagsTask'
import { AdminBulkEditTask } from './tasks/adminBulkEdit/AdminBulkEditTask'
import { TagReverseLookupTask } from './tasks/tagReverseLookup/TagReverseLookupTask'
import { MichinekiNearbyTask } from './tasks/michinekiNearby/MichinekiNearbyTask'

type ActiveTask = 'home' | TaskType

const TASK_MENU: Array<{ group: string; items: Array<{ id: TaskType; label: string; icon: string; desc: string; admin?: boolean }> }> = [
  {
    group: '通常作業',
    items: [
      { id: 'add_municipality_url', label: '自治体URLを追加する', icon: '🏛', desc: '市区町村の公式案内ページ' },
      { id: 'assign_all_tags', label: '全タグを付ける', icon: '🏷', desc: '場所・駅・観光 すべてのタグ＋OSM連携・施設名設定' },
      { id: 'tag_reverse_lookup', label: 'タグ別マンホール一覧', icon: '🔍', desc: 'タグごとに設定済みマンホールを逆引き' },
      { id: 'michineki_nearby', label: '道の駅 300m圏内', icon: '🏪', desc: '道の駅と300m以内のポケふたを一覧・紐づけ' },
    ],
  },
  {
    group: 'Admin',
    items: [
      { id: 'verify_official_url', label: '公式URLを確認する', icon: '🔗', desc: 'official_url フィールド', admin: true },
      { id: 'admin_bulk_edit', label: '一括編集', icon: '⚙️', desc: '複数件を条件で一括変更', admin: true },
    ],
  },
]

const ALL_TASK_IDS = new Set<string>(TASK_MENU.flatMap(g => g.items.map(i => i.id)))

function hashToTask(hash: string): ActiveTask {
  const id = hash.replace(/^#/, '')
  return (ALL_TASK_IDS.has(id) ? id : 'home') as ActiveTask
}

function taskToHash(task: ActiveTask): string {
  return task === 'home' ? '#home' : `#${task}`
}

export default function App() {
  const [activeTask, setActiveTaskState] = useState<ActiveTask>(() => hashToTask(window.location.hash))
  const [editInitialSearch, setEditInitialSearch] = useState<string | undefined>(undefined)
  const [titles, setTitles] = useState<ManholeTitlesJson | null>(null)
  const [records, setRecords] = useState<PokefutaRecord[]>([])
  const [sessionPatches, setSessionPatches] = useState<SemanticPatch[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [prStatus, setPrStatus] = useState<string | null>(null)
  const [prRunning, setPrRunning] = useState(false)

  // URL hash → state sync (browser back/forward)
  useEffect(() => {
    const onHashChange = () => setActiveTaskState(hashToTask(window.location.hash))
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const setActiveTask = useCallback((task: ActiveTask) => {
    window.location.hash = taskToHash(task)
    setActiveTaskState(task)
  }, [])

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

  function handleNavigateToEdit(manholeId: string) {
    setEditInitialSearch(manholeId)
    setActiveTask('assign_all_tags')
  }

  function navigate(task: ActiveTask) {
    setEditInitialSearch(undefined)
    setActiveTask(task)
  }

  function renderTask() {
    if (!titles) return null
    switch (activeTask) {
      case 'assign_all_tags':
        return <AssignAllTagsTask {...commonProps} titles={titles} onSaveMany={handleSavePatches} initialSearch={editInitialSearch} />
      case 'add_municipality_url':
        return <AddMunicipalityUrlTask {...commonProps} titles={titles} onSave={handleSavePatch} />
      case 'verify_official_url':
        return <VerifyOfficialUrlTask {...commonProps} titles={titles} onSave={handleSavePatch} />
      case 'admin_bulk_edit':
        return <AdminBulkEditTask {...commonProps} titles={titles} onSaveMany={handleSavePatches} />
      case 'tag_reverse_lookup':
        return <TagReverseLookupTask titles={titles} records={records} onNavigateToEdit={handleNavigateToEdit} />
      case 'michineki_nearby':
        return <MichinekiNearbyTask {...commonProps} titles={titles} onSaveMany={handleSavePatches} />
      default:
        return <Home onSelectTask={navigate} />
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
            <a
              href="#home"
              className={`task-menu-link${activeTask === 'home' ? ' active' : ''}`}
              onClick={() => setEditInitialSearch(undefined)}
            >
              🏠 ホーム
            </a>
          </li>
          {TASK_MENU.map(group => (
            <li key={group.group}>
              <div className="task-menu-group">{group.group}</div>
              <ul className="task-menu" style={{ padding: 0 }}>
                {group.items.map(item => (
                  <li key={item.id}>
                    <a
                      href={`#${item.id}`}
                      className={`task-menu-link${activeTask === item.id ? ' active' : ''}`}
                      onClick={() => setEditInitialSearch(undefined)}
                    >
                      {item.icon} {item.label}
                    </a>
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
