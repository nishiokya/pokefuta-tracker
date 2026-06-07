import type { SemanticPatch, ManholeTitlesJson } from './semanticPatch'
import { normCity } from './semanticPatchApplier'

export type ValidationResult = {
  valid: boolean
  warnings: string[]
  errors: string[]
}

const VALID_TAGS = new Set([
  'seaside', 'beach', 'lakeside', 'river', 'remote_island', 'roadside',
  'in_station', 'station_front', 'near_station', 'rail_access_good', 'far_station',
  'tourism', 'park', 'museum', 'history', 'food', 'world_heritage',
])

export function validatePatch(
  patch: SemanticPatch,
  titles: ManholeTitlesJson
): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  if (patch.target === 'manholes') {
    if (!patch.manholeIds?.length) {
      errors.push('manholeIds is required for manholes target')
    }
    for (const id of patch.manholeIds ?? []) {
      // ID existence check is a warning, not error (new IDs can be added)
      const strId = String(id)
      if (!Object.prototype.hasOwnProperty.call(titles.manholes, strId)) {
        warnings.push(`id ${id} has no existing manhole entry (will be created)`)
      }
    }
    if (patch.operation === 'add_tags' || patch.operation === 'remove_tags') {
      const tags = (patch.payload.tags as string[]) ?? []
      for (const tag of tags) {
        if (!VALID_TAGS.has(tag)) {
          warnings.push(`unknown tag "${tag}" — not in vocabulary`)
        }
      }
    }
  }

  if (patch.target === 'city_links') {
    if (!patch.cityLinkEntry) {
      errors.push('cityLinkEntry is required for city_links target')
    } else {
      const { prefecture, city, url } = patch.cityLinkEntry
      if (!prefecture || !city || !url) {
        errors.push('cityLinkEntry must have prefecture, city, and url')
      }
      const existing = titles.city_links.find(
        cl =>
          cl.prefecture === prefecture &&
          normCity(cl.city) === normCity(city)
      )
      if (existing && existing.url === url) {
        warnings.push(
          `city_link for ${prefecture}/${city} already exists with same URL`
        )
      }
      if (url && !url.startsWith('http')) {
        errors.push('url must start with http/https')
      }
    }
  }

  return { valid: errors.length === 0, errors, warnings }
}
