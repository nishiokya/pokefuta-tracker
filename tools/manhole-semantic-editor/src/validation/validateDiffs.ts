export type DiffValidationResult = {
  safe: boolean
  violations: string[]
}

const FORBIDDEN_PATTERNS = [
  /^docs\/.*\.ndjson$/,
  /^apps\/scraper\/.*\.ndjson$/,
]

const ALLOWED_FILES = new Set(['dataset/manhole_titles.json'])

export function checkDiffOutput(gitDiffOutput: string): DiffValidationResult {
  const violations: string[] = []
  const lines = gitDiffOutput.trim().split('\n').filter(Boolean)

  for (const line of lines) {
    const file = line.trim()
    if (!file) continue

    for (const pattern of FORBIDDEN_PATTERNS) {
      if (pattern.test(file)) {
        violations.push(`FORBIDDEN: ${file} (crawler-owned data must not be modified)`)
      }
    }

    if (!ALLOWED_FILES.has(file) && !FORBIDDEN_PATTERNS.some(p => p.test(file))) {
      violations.push(`UNEXPECTED: ${file} (only dataset/manhole_titles.json should be changed)`)
    }
  }

  return { safe: violations.length === 0, violations }
}
