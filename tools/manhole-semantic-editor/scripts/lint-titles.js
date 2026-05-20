#!/usr/bin/env node
/**
 * Normalize dataset/manhole_titles.json to the Editor's canonical form.
 *
 * Applies the same serialization rules as src/semantic/semanticPatchApplier.ts
 * serializeTitles() — id-sorted manholes, fixed field order, 2-space indent,
 * trailing newline. Running this once on a file means subsequent Editor saves
 * produce minimal diffs (only the semantic change, no reorder noise).
 *
 * Usage:
 *   node scripts/lint-titles.js           # apply in place
 *   node scripts/lint-titles.js --check   # exit 1 if not canonical
 */
import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const TITLES_PATH = path.resolve(__dirname, '../../../dataset/manhole_titles.json')

const MANHOLE_KEY_ORDER = [
  'building',
  'address_raw',
  'address_norm',
  'prefecture',
  'city',
  'place_detail',
  'verified_at',
  'tags',
  'confidence',
  'official_url',
]

function reorderKeys(entry) {
  const result = {}
  for (const key of MANHOLE_KEY_ORDER) {
    if (key in entry && entry[key] !== undefined) result[key] = entry[key]
  }
  // Defensive: keep unknown keys at the end with a warning (data shouldn't be lost)
  for (const key of Object.keys(entry)) {
    if (!MANHOLE_KEY_ORDER.includes(key) && entry[key] !== undefined) {
      console.warn(`⚠️  unknown manhole field "${key}" — preserving at end`)
      result[key] = entry[key]
    }
  }
  return result
}

function serializeTitles(data) {
  const sortedManholes = Object.fromEntries(
    Object.entries(data.manholes)
      .sort(([a], [b]) => parseInt(a, 10) - parseInt(b, 10))
      .map(([id, entry]) => [id, reorderKeys(entry)])
  )
  const sorted = { ...data, manholes: sortedManholes }
  return JSON.stringify(sorted, null, 2) + '\n'
}

const checkOnly = process.argv.includes('--check')
const raw = fs.readFileSync(TITLES_PATH, 'utf-8')
const data = JSON.parse(raw)
const normalized = serializeTitles(data)

if (raw === normalized) {
  console.log('✅ already canonical, no changes needed')
  process.exit(0)
}

if (checkOnly) {
  const before = raw.split('\n').length
  const after = normalized.split('\n').length
  console.error(`❌ not canonical (lines ${before} → ${after})`)
  console.error('   run: node scripts/lint-titles.js')
  process.exit(1)
}

fs.writeFileSync(TITLES_PATH, normalized, 'utf-8')
const beforeLines = raw.split('\n').length
const afterLines = normalized.split('\n').length
console.log(`✅ linted dataset/manhole_titles.json (lines ${beforeLines} → ${afterLines})`)
