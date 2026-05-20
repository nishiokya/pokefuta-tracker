import type { ManholeTitlesJson } from '../semantic/semanticPatch'

export type SchemaValidationResult = {
  valid: boolean
  errors: string[]
}

export function validateTitlesSchema(data: unknown): SchemaValidationResult {
  const errors: string[] = []

  if (!data || typeof data !== 'object') {
    return { valid: false, errors: ['root must be an object'] }
  }

  const obj = data as Record<string, unknown>

  if (typeof obj.version !== 'number') {
    errors.push('version must be a number')
  }
  if (!obj.vocabulary || typeof obj.vocabulary !== 'object') {
    errors.push('vocabulary must be an object')
  }
  if (!Array.isArray(obj.islands)) {
    errors.push('islands must be an array')
  }
  if (!Array.isArray(obj.city_links)) {
    errors.push('city_links must be an array')
  }
  if (!obj.manholes || typeof obj.manholes !== 'object') {
    errors.push('manholes must be an object')
  } else {
    for (const [id, entry] of Object.entries(obj.manholes)) {
      if (isNaN(parseInt(id, 10))) {
        errors.push(`manholes key "${id}" is not a numeric ID`)
      }
      if (entry && typeof entry === 'object') {
        const e = entry as Record<string, unknown>
        if (e.tags !== undefined && !Array.isArray(e.tags)) {
          errors.push(`manholes.${id}.tags must be an array`)
        }
        if (
          e.confidence !== undefined &&
          typeof e.confidence !== 'number'
        ) {
          errors.push(`manholes.${id}.confidence must be a number`)
        }
      }
    }
  }

  for (const [i, cl] of ((obj.city_links as unknown[]) ?? []).entries()) {
    if (!cl || typeof cl !== 'object') {
      errors.push(`city_links[${i}] must be an object`)
      continue
    }
    const c = cl as Record<string, unknown>
    if (!c.prefecture || !c.city || !c.url) {
      errors.push(
        `city_links[${i}] must have prefecture, city, and url`
      )
    }
  }

  return { valid: errors.length === 0, errors }
}

export function assertValidTitles(data: unknown): ManholeTitlesJson {
  const result = validateTitlesSchema(data)
  if (!result.valid) {
    throw new Error(
      `manhole_titles.json schema error:\n${result.errors.join('\n')}`
    )
  }
  return data as ManholeTitlesJson
}
