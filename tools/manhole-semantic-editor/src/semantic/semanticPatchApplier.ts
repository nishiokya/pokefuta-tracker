import type {
  SemanticPatch,
  ManholeTitlesJson,
  ManholeEntry,
  CityLinkEntry,
} from './semanticPatch'

const MANHOLE_KEY_ORDER: (keyof ManholeEntry)[] = [
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

const CONFIDENCE_MAP: Record<string, number> = {
  low: 1,
  medium: 2,
  high: 3,
  verified: 4,
}

export function normCity(city: string): string {
  return city.replace(/[市区町村郡]$/, '')
}

function reorderKeys(entry: ManholeEntry): ManholeEntry {
  const result: Record<string, unknown> = {}
  for (const key of MANHOLE_KEY_ORDER) {
    if (key in entry && entry[key] !== undefined) {
      result[key] = entry[key]
    }
  }
  return result as ManholeEntry
}

export function serializeTitles(data: ManholeTitlesJson): string {
  const sortedManholes = Object.fromEntries(
    Object.entries(data.manholes)
      .sort(([a], [b]) => parseInt(a, 10) - parseInt(b, 10))
      .map(([id, entry]) => [id, reorderKeys(entry)])
  )
  const sorted: ManholeTitlesJson = { ...data, manholes: sortedManholes }
  return JSON.stringify(sorted, null, 2) + '\n'
}

export function applyPatch(
  titles: ManholeTitlesJson,
  patch: SemanticPatch
): ManholeTitlesJson {
  const updated: ManholeTitlesJson = structuredClone(titles)

  if (patch.target === 'city_links') {
    return applyCityLinkPatch(updated, patch)
  }
  if (patch.target === 'manholes') {
    return applyManholePatch(updated, patch)
  }
  return updated
}

function applyCityLinkPatch(
  titles: ManholeTitlesJson,
  patch: SemanticPatch
): ManholeTitlesJson {
  if (patch.operation === 'set_municipality_url' && patch.cityLinkEntry) {
    const { prefecture, city, url } = patch.cityLinkEntry
    const idx = titles.city_links.findIndex(
      cl =>
        cl.prefecture === prefecture &&
        normCity(cl.city) === normCity(city)
    )
    const entry: CityLinkEntry = { prefecture, city, url }
    if (idx >= 0) {
      titles.city_links[idx] = entry
    } else {
      // Insert after the last entry with the same prefecture to keep prefecture blocks contiguous
      let insertAt = titles.city_links.length
      for (let i = titles.city_links.length - 1; i >= 0; i--) {
        if (titles.city_links[i].prefecture === prefecture) {
          insertAt = i + 1
          break
        }
      }
      titles.city_links.splice(insertAt, 0, entry)
    }
  }
  return titles
}

function applyManholePatch(
  titles: ManholeTitlesJson,
  patch: SemanticPatch
): ManholeTitlesJson {
  const ids = (patch.manholeIds ?? []).map(String)

  for (const id of ids) {
    if (!titles.manholes[id]) {
      titles.manholes[id] = {}
    }
    const entry = titles.manholes[id]

    switch (patch.operation) {
      case 'add_tags': {
        const newTags = (patch.payload.tags as string[]) ?? []
        const existing = entry.tags ?? []
        entry.tags = [...new Set([...existing, ...newTags])]
        break
      }
      case 'remove_tags': {
        const removeTags = (patch.payload.tags as string[]) ?? []
        entry.tags = (entry.tags ?? []).filter(t => !removeTags.includes(t))
        if (entry.tags.length === 0) delete entry.tags
        break
      }
      case 'set_official_url': {
        entry.official_url = patch.payload.url as string
        if (!entry.official_url) delete entry.official_url
        break
      }
      case 'set_confidence': {
        entry.confidence = CONFIDENCE_MAP[patch.confidence ?? 'low'] ?? 1
        if (patch.payload.verified_at) {
          entry.verified_at = patch.payload.verified_at as string
        }
        break
      }
      case 'set_title': {
        if (patch.payload.building !== undefined)
          entry.building = patch.payload.building as string
        if (patch.payload.place_detail !== undefined)
          entry.place_detail = patch.payload.place_detail as string
        if (!entry.building) delete entry.building
        if (!entry.place_detail) delete entry.place_detail
        break
      }
      case 'set_address': {
        if (patch.payload.address_norm !== undefined)
          entry.address_norm = patch.payload.address_norm as string
        break
      }
    }

    // Remove empty manhole entry
    if (Object.keys(entry).length === 0) {
      delete titles.manholes[id]
    }
  }
  return titles
}

export function generateConfirmationText(patch: SemanticPatch): string {
  const count = patch.manholeIds?.length ?? 0
  switch (patch.operation) {
    case 'add_tags': {
      const tags = ((patch.payload.tags as string[]) ?? [])
        .join(', ')
        .toUpperCase()
      return `ADD TAG ${tags} TO ${count} MANHOLES`
    }
    case 'remove_tags': {
      const tags = ((patch.payload.tags as string[]) ?? [])
        .join(', ')
        .toUpperCase()
      return `REMOVE TAG ${tags} FROM ${count} MANHOLES`
    }
    case 'set_official_url':
      return `SET OFFICIAL URL FOR ${count} MANHOLES`
    case 'set_municipality_url':
      return `ADD CITY LINK FOR ${patch.cityLinkEntry?.city ?? '?'}`
    default:
      return `CONFIRM BULK EDIT OF ${count} MANHOLES`
  }
}
