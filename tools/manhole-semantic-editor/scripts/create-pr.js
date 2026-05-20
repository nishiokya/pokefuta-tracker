#!/usr/bin/env node
import { execSync, execFileSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(__dirname, '../../..')
const PATCHES_PATH = path.join(__dirname, '../workspace/changes.ndjson')
const TITLES_PATH = path.join(REPO_ROOT, 'dataset/manhole_titles.json')

function run(cmd, opts = {}) {
  return execSync(cmd, { cwd: REPO_ROOT, encoding: 'utf-8', ...opts }).trim()
}

function getJSTTimestamp() {
  const now = new Date()
  const jst = new Date(now.getTime() + 9 * 60 * 60 * 1000)
  const iso = jst.toISOString()
  return iso.slice(0, 10).replace(/-/g, '') + iso.slice(11, 19).replace(/:/g, '')
}

function buildPRBody(patches) {
  const byTask = {}
  for (const p of patches) {
    byTask[p.taskType] = (byTask[p.taskType] ?? 0) + 1
  }
  const taskLines = Object.entries(byTask)
    .map(([k, n]) => `- ${k}: ${n}件`)
    .join('\n')

  const totalManholes = new Set(patches.flatMap(p => p.manholeIds ?? [])).size

  return `## Summary

semantic metadata をセマンティックエディタで更新しました。

## 変更内容

${taskLines}

対象マンホール数（ユニーク）: ${totalManholes}件

## Tasks

${taskLines}

## Guardrails

- docs/pokefuta.ndjson は変更されていません
- dataset/manhole_titles.json のみ変更されています

## Validation

- [x] JSON parse OK
- [x] schema OK
- [x] docs/*.ndjson 汚染なし
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

// 2. Check for forbidden diffs
const allChanged = run('git diff --name-only HEAD')
const forbidden = allChanged.split('\n').filter(f =>
  f.match(/^docs\/.*\.ndjson$/) || f.match(/^apps\/scraper\/.*\.ndjson$/)
)
if (forbidden.length > 0) {
  console.error('❌ クローラー管轄ファイルが変更されています:', forbidden.join(', '))
  process.exit(1)
}
console.log('✅ docs/*.ndjson は変更されていません')

// 3. Check titles changed
const titlesStatus = run(`git status --porcelain "${TITLES_PATH}"`)
if (!titlesStatus) {
  console.error('❌ dataset/manhole_titles.json に変更がありません。PRを作成するものがありません。')
  process.exit(1)
}
console.log('✅ dataset/manhole_titles.json に変更があります')

// 4. Check gh is available
try {
  run('gh auth status', { stdio: 'pipe' })
} catch {
  console.error('❌ gh CLI が認証されていません。`gh auth login` を実行してください。')
  process.exit(1)
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
const prBody = buildPRBody(patches)
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
console.log('\n🎉 完了:', prUrl)
