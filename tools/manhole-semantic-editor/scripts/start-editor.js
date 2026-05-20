#!/usr/bin/env node
import { execFileSync } from 'node:child_process'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const editorDir = path.join(__dirname, '..')

console.log('Starting Manhole Semantic Editor on http://localhost:5177')
console.log('Press Ctrl+C to stop.')

execFileSync('npm', ['run', 'dev'], {
  cwd: editorDir,
  stdio: 'inherit',
})
