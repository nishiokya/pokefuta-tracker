export const VALID_TAGS = [
  'seaside', 'beach', 'lakeside', 'river', 'remote_island', 'roadside',
  'in_station', 'station_front', 'near_station', 'rail_access_good', 'far_station',
  'tourism', 'park', 'museum', 'history', 'food', 'world_heritage',
  'near_gundam_manhole', 'gundam_manhole_city',
] as const

export type ValidTag = (typeof VALID_TAGS)[number]
