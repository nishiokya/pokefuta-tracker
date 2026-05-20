#!/usr/bin/env node
import { execSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(__dirname, '../../..')
const PATCHES_PATH = path.join(__dirname, '../workspace/changes.ndjson')

let hasError = false

function fail(msg) {
  console.error('❌', msg)
  hasError = true
}

function ok(msg) {
  console.log('✅', msg)
}

// 1. Check workspace/changes.ndjson is valid NDJSON
if (!fs.existsSync(PATCHES_PATH)) {
  fail('workspace/changes.ndjson が存在しません。セッション中に変更が加えられていません。')
} else {
  const raw = fs.readFileSync(PATCHES_PATH, 'utf-8').trim()
  if (!raw) {
    fail('workspace/changes.ndjson が空です。変更がありません。')
  } else {
    const lines = raw.split('\n').filter(Boolean)
    let parseOk = true
    for (const [i, line] of lines.entries()) {
      try { JSON.parse(line) } catch {
        fail(`changes.ndjson の ${i + 1} 行目が不正な JSON です`)
        parseOk = false
      }
    }
    if (parseOk) ok(`changes.ndjson: ${lines.length}件のパッチが有効`)
  }
}

// 2. Check git diff for forbidden files
try {
  const allChanged = execSync('git diff --name-only HEAD', { cwd: REPO_ROOT }).toString().trim()
  const staged = execSync('git diff --cached --name-only', { cwd: REPO_ROOT }).toString().trim()
  const changedFiles = [...new Set([
    ...allChanged.split('\n').filter(Boolean),
    ...staged.split('\n').filter(Boolean),
  ])]

  const forbidden = changedFiles.filter(f =>
    f.match(/^docs\/.*\.ndjson$/) || f.match(/^apps\/scraper\/.*\.ndjson$/)
  )
  if (forbidden.length > 0) {
    fail(`クローラー管轄ファイルが変更されています:\n  ${forbidden.join('\n  ')}`)
  } else {
    ok('docs/*.ndjson は変更されていません')
  }

  const titlesChanged = changedFiles.some(f => f === 'dataset/manhole_titles.json')
  if (!titlesChanged) {
    console.warn('⚠️  dataset/manhole_titles.json に変更がありません（PR作成はスキップされます）')
  } else {
    ok('dataset/manhole_titles.json が変更されています')
  }

  // Warn about unexpected files
  const unexpected = changedFiles.filter(f =>
    f !== 'dataset/manhole_titles.json' &&
    !f.match(/^docs\/.*\.ndjson$/) &&
    !f.match(/^apps\/scraper\/.*\.ndjson$/)
  )
  if (unexpected.length > 0) {
    console.warn('⚠️  予期しないファイルが変更されています:', unexpected.join(', '))
  }
} catch (e) {
  fail(`git diff の実行に失敗しました: ${e.message}`)
}

if (hasError) {
  process.exit(1)
} else {
  console.log('\n✅ バリデーション完了')
}
