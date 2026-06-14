export type TaskType =
  | 'add_municipality_url'
  | 'verify_official_url'
  | 'assign_all_tags'
  | 'assign_location_tags'
  | 'assign_station_tags'
  | 'assign_tourism_tags'
  | 'verify_title'
  | 'admin_edit_manhole'
  | 'admin_bulk_edit'
  | 'tag_reverse_lookup'
  | 'michineki_nearby'
  | 'manholemap_nearby'
  | 'gmanhole_geocoder'

export type OperationType =
  | 'set_municipality_url'
  | 'set_official_url'
  | 'add_tags'
  | 'remove_tags'
  | 'set_title'
  | 'set_confidence'
  | 'set_address'
  | 'set_gmanhole_override'

export type ConfidenceLevel = 'low' | 'medium' | 'high' | 'verified'

export type PatchTarget = 'manholes' | 'gmanholes' | 'city_links' | 'islands' | 'lakes'

export type CityLinkEntry = {
  prefecture: string
  city: string
  url: string
}

export type SemanticPatch = {
  id: string
  createdAt: string
  taskType: TaskType
  operation: OperationType
  target: PatchTarget
  manholeIds?: number[]
  cityLinkEntry?: CityLinkEntry
  payload: Record<string, unknown>
  note?: string
  confidence?: ConfidenceLevel
}

export type VocabularyEntry = {
  enabled: boolean
  emoji: string
  label: string
  hashtag: string
  priority: number
  hashtag_extra?: string
  id_threshold?: number
  note?: string
}

export type IslandEntry = {
  island: string
  prefecture: string
  city: string | null
  ids?: string[]
  note?: string
}

export type LakeEntry = {
  lake: string
  prefecture?: string
  ids: string[]
}

export type ManholeEntry = {
  building?: string
  address_raw?: string
  address_norm?: string
  prefecture?: string
  city?: string
  place_detail?: string
  verified_at?: string
  tags?: string[]
  confidence?: number
  official_url?: string
}

export type ManholeTitlesJson = {
  _doc: string
  version: number
  vocabulary: Record<string, VocabularyEntry>
  islands: IslandEntry[]
  city_links: CityLinkEntry[]
  manholes: Record<string, ManholeEntry>
  lakes?: LakeEntry[]
}

export type TitleBadge = {
  key: string
  label: string
  emoji: string
  hashtag: string
  priority: number
}

export type PokefutaRecord = {
  id: string
  title: string
  prefecture: string
  city: string
  address: string
  city_url: string
  lat: number
  lng: number
  pokemons: string[]
  detail_url: string
  prefecture_site_url: string
  first_seen: string
  added_at: string
  last_updated: string
  status: 'active' | 'deleted'
  is_prefecture_site: boolean
  building: string
  tags?: string[]
  titles?: TitleBadge[]
}

// Agent extension types (future use)
export type AgentTaskType =
  | 'find_station_proximity'
  | 'find_municipality_official_url'
  | 'find_seaside_candidates'
  | 'find_remote_island_candidates'

export type AgentProposal = {
  proposalId: string
  agentTaskType: AgentTaskType
  patches: SemanticPatch[]
  reasoning: string
  createdAt: string
  status: 'pending' | 'accepted' | 'rejected'
  evidence: Array<{
    type: string
    url?: string
    note?: string
  }>
  confidence: ConfidenceLevel
}
