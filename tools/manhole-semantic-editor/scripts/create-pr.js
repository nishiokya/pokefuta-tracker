#!/usr/bin/env node
import { execSync, execFileSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(__dirname, '../../..')
const PATCHES_PATH = path.join(__dirname, '../workspace/changes.ndjson')
const TITLES_PATH = path.join(REPO_ROOT, 'dataset/manhole_titles.json')
const GMANHOLE_FILES = [
  'apps/tools/geocode_gmanhole.py',
  'apps/tools/test_geocode_gmanhole.py',
  'dataset/gmanhole_overrides.json',
  'dataset/gmanhole_geocode_audit.json',
  'docs/gmanhole.ndjson',
  'gmanhole_geocode_cache.json',
  'tools/manhole-semantic-editor/README.md',
  'tools/manhole-semantic-editor/scripts/create-pr.js',
  'tools/manhole-semantic-editor/scripts/validate-editor-changes.js',
  'tools/manhole-semantic-editor/src/App.tsx',
  'tools/manhole-semantic-editor/src/semantic/semanticPatch.ts',
  'tools/manhole-semantic-editor/src/tasks/gmanholeGeocoder/GmanholeGeocoderTask.tsx',
  'tools/manhole-semantic-editor/vite.config.ts',
]

function run(cmd, opts = {}) {
  return execSync(cmd, { cwd: REPO_ROOT, encoding: 'utf-8', ...opts }).trim()
}

function getJSTTimestamp() {
  const now = new Date()
  const jst = new Date(now.getTime() + 9 * 60 * 60 * 1000)
  const iso = jst.toISOString()
  return iso.slice(0, 10).replace(/-/g, '') + iso.slice(11, 19).replace(/:/g, '')
}

function buildPRBody(patches, mode) {
  const byTask = {}
  for (const p of patches) {
    byTask[p.taskType] = (byTask[p.taskType] ?? 0) + 1
  }
  const taskLines = Object.entries(byTask)
    .map(([k, n]) => `- ${k}: ${n}件`)
    .join('\n')

  const totalManholes = new Set(patches.flatMap(p => p.manholeIds ?? [])).size

  const guardrails = mode === 'gmanhole'
    ? '- ガンダム座標管理に必要なファイルだけをコミット\n- 写真JSONなど既存の無関係な変更は含めていません'
    : '- docs/pokefuta.ndjson は変更されていません\n- dataset/manhole_titles.json のみ変更されています'

  return `## Summary

semantic metadata をセマンティックエディタで更新しました。

## 変更内容

${taskLines}

対象マンホール数（ユニーク）: ${totalManholes}件

## Tasks

${taskLines}

## Guardrails

${guardrails}

## Validation

- [x] JSON parse OK
- [x] schema OK
- [x] changes.ndjson で操作ログ確認済み

🤖 Generated with Semantic Manhole Metadata Editor`
}

// --- Main ---

// 1. Check patches
if (!fs.existsSync(PATCHES_PATH)) {
  console.error('❌ workspace/changes.ndjson が存在しません。変更がありません。')
  process.exit(1)
}
const patchesRaw = fs.readFileSync(PATCHES_PATH, 'utf-8').trim()
if (!patchesRaw) {
  console.error('❌ workspace/changes.ndjson が空です。変更がありません。')
  process.exit(1)
}
const patches = patchesRaw.split('\n').filter(Boolean).map(l => JSON.parse(l))
console.log(`✅ ${patches.length}件のパッチを読み込みました`)
const isGmanholeMode = patches.some(p => p.taskType === 'gmanhole_geocoder')
const isTitlesMode = patches.some(p => p.taskType !== 'gmanhole_geocoder')
if (isGmanholeMode && isTitlesMode) {
  console.error('❌ ガンダム座標編集と通常のsemantic編集は別々にPRを作成してください。')
  process.exit(1)
}
const mode = isGmanholeMode ? 'gmanhole' : 'titles'

// 2. Check for forbidden diffs
const allChanged = run('git diff --name-only HEAD')
const forbidden = allChanged.split('\n').filter(f =>
  (f.match(/^docs\/.*\.ndjson$/) && !(mode === 'gmanhole' && f === 'docs/gmanhole.ndjson'))
  || f.match(/^apps\/scraper\/.*\.ndjson$/)
)
if (forbidden.length > 0) {
  console.error('❌ クローラー管轄ファイルが変更されています:', forbidden.join(', '))
  process.exit(1)
}
console.log('✅ 禁止対象のNDJSONは変更されていません')

// 3. Check titles changed
const titlesStatus = mode === 'titles' ? run(`git status --porcelain "${TITLES_PATH}"`) : ''
const gmanholeStatus = mode === 'gmanhole'
  ? run(`git status --porcelain -- ${GMANHOLE_FILES.map(file => `"${file}"`).join(' ')}`)
  : ''
if (mode === 'titles' && !titlesStatus) {
  console.error('❌ dataset/manhole_titles.json に変更がありません。PRを作成するものがありません。')
  process.exit(1)
}
if (mode === 'gmanhole' && !gmanholeStatus) {
  console.error('❌ ガンダム座標関連ファイルに変更がありません。')
  process.exit(1)
}
console.log(mode === 'gmanhole'
  ? '✅ ガンダム座標関連ファイルに変更があります'
  : '✅ dataset/manhole_titles.json に変更があります')

// 4. Check gh is available
try {
  run('gh auth status', { stdio: 'pipe' })
} catch {
  console.error('❌ gh CLI が認証されていません。`gh auth login` を実行してください。')
  process.exit(1)
}

if (mode === 'gmanhole') {
  const branch = run('git rev-parse --abbrev-ref HEAD')
  if (branch === 'main') {
    console.error('❌ ガンダム座標編集は作業ブランチ上でPRを作成してください。')
    process.exit(1)
  }
  run(`git add -- ${GMANHOLE_FILES.map(file => `"${file}"`).join(' ')}`)
  run(`git commit -m "Manage verified Gundam manhole locations"`)
  console.log('✅ コミット完了')
  run(`git push -u origin ${branch}`)
  console.log('✅ プッシュ完了')
  const prBody = buildPRBody(patches, mode)
  const prBodyFile = path.join(__dirname, '../workspace/pr_body.tmp.md')
  fs.writeFileSync(prBodyFile, prBody, 'utf-8')
  let prUrl = ''
  try {
    prUrl = run(`gh pr create --title "Manage verified Gundam manhole locations" --body-file "${prBodyFile}"`)
  } finally {
    fs.existsSync(prBodyFile) && fs.unlinkSync(prBodyFile)
  }
  fs.writeFileSync(PATCHES_PATH, '', 'utf-8')
  console.log('✅ workspace/changes.ndjson をクリアしました')
  console.log('\n🎉 完了:', prUrl)
  process.exit(0)
}

// 5. Save the Editor's output, then base new branch on fresh main
// This prevents stacking on previous unmerged edit branches.
const editorOutput = fs.readFileSync(TITLES_PATH, 'utf-8')
console.log(`📋 Editor 出力を退避 (${editorOutput.length} bytes)`)

const previousBranch = run('git rev-parse --abbrev-ref HEAD')
const branch = `edit/manhole-titles-${getJSTTimestamp()}`

try {
  run('git fetch origin main', { stdio: 'pipe' })
} catch (e) {
  console.error('❌ git fetch origin main 失敗:', e.message)
  process.exit(1)
}

// Discard working copy modification of titles before switching (we have it in memory)
run(`git checkout -- "${TITLES_PATH}"`)

// Stash any other uncommitted changes so git checkout main succeeds
const otherDirty = run('git status --porcelain').split('\n').filter(l => l.trim() && !l.includes('changes.ndjson'))
const needsStash = otherDirty.length > 0
if (needsStash) {
  run('git stash push --include-untracked -m "create-pr-temp"')
  console.log('📦 他の変更を一時stashしました')
}

run('git checkout main')
try {
  run('git pull origin main --ff-only', { stdio: 'pipe' })
} catch {
  console.warn('⚠️  main の pull に失敗。ローカル main を使用します。')
}

console.log(`📌 main から新ブランチを作成: ${branch} (previous: ${previousBranch})`)
run(`git checkout -b ${branch}`)

// Apply Editor output on top of fresh main
fs.writeFileSync(TITLES_PATH, editorOutput, 'utf-8')

// 6. Stage and commit
run(`git add "${TITLES_PATH}"`)
const commitMsg = `edit: manhole-titles semantic edits ${getJSTTimestamp().slice(0, 8)}`
run(`git commit -m "${commitMsg}"`)
console.log('✅ コミット完了')

// 7. Push
run(`git push -u origin ${branch}`)
console.log('✅ プッシュ完了')

// 8. Create PR
const prBody = buildPRBody(patches, mode)
const prTitle = `Update manhole semantic metadata (${getJSTTimestamp().slice(0, 8)})`
const prBodyFile = path.join(__dirname, '../workspace/pr_body.tmp.md')
fs.writeFileSync(prBodyFile, prBody, 'utf-8')

let prUrl = ''
try {
  prUrl = run(`gh pr create --title "${prTitle}" --body-file "${prBodyFile}"`)
  fs.unlinkSync(prBodyFile)
} catch (e) {
  fs.existsSync(prBodyFile) && fs.unlinkSync(prBodyFile)
  console.error('❌ PR作成に失敗しました:', e.message)
  process.exit(1)
}

console.log('✅ PR作成完了:', prUrl)

// 9. Clear session patches
fs.writeFileSync(PATCHES_PATH, '', 'utf-8')
console.log('✅ workspace/changes.ndjson をクリアしました')

// 10. Return to previous branch and restore stash
run(`git checkout ${previousBranch}`)
if (needsStash) {
  try {
    run('git stash pop')
    console.log('📦 stashを復元しました')
  } catch (e) {
    console.warn('⚠️  stash popに失敗しました。手動で `git stash pop` を実行してください。', e.message)
  }
}

console.log('\n🎉 完了:', prUrl)
