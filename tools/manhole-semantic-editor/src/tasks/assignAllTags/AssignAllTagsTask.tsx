import type { PokefutaRecord, ManholeTitlesJson, SemanticPatch } from '../../semantic/semanticPatch'
import { MapTagsTask } from '../shared/MapTagsTask'
import type { OsmPoiConfig, TagGroup } from '../shared/MapTagsTask'

const TAG_GROUPS: TagGroup[] = [
  {
    label: '📍 場所',
    tags: ['seaside', 'beach', 'lakeside', 'river', 'remote_island', 'roadside'],
  },
  {
    label: '🚉 駅',
    tags: ['in_station', 'station_front', 'near_station', 'rail_access_good', 'far_station'],
  },
  {
    label: '🗺 観光',
    tags: ['tourism', 'park', 'museum', 'history', 'food', 'world_heritage'],
  },
]

const TAG_LABELS: Record<string, string> = {
  seaside: '🌊 海沿い',
  beach: '🏖 ビーチ',
  lakeside: '🏞 湖畔',
  river: '🌊 川沿い',
  remote_island: '🏝 離島',
  roadside: '🛣 道の駅',
  in_station: '🚉 駅構内',
  station_front: '🏢 駅前',
  near_station: '🚶 駅近',
  rail_access_good: '🚆 アクセス良',
  far_station: '🚗 駅から遠い',
  tourism: '🗺 観光',
  park: '🌳 公園',
  museum: '🏛 博物館',
  history: '🏯 歴史',
  food: '🍜 グルメ',
  world_heritage: '🏯 世界遺産',
}

const OSM_CONFIGS: OsmPoiConfig[] = [
  { type: 'michineki', label: '道の駅', defaultTag: 'roadside', radiusM: 200 },
  {
    type: 'station',
    label: '駅',
    defaultTag: (d) => d < 50 ? 'in_station' : d < 200 ? 'station_front' : 'near_station',
    radiusM: 100,
  },
  { type: 'museum', label: '博物館', defaultTag: 'museum', radiusM: 100 },
  { type: 'park', label: '公園', defaultTag: 'park', radiusM: 100 },
]

type Props = {
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSaveMany: (patches: SemanticPatch[]) => Promise<void>
  saving: boolean
  initialSearch?: string
}

export function AssignAllTagsTask({ initialSearch, ...props }: Props) {
  return (
    <MapTagsTask
      {...props}
      title="全タグを付ける"
      taskType="assign_all_tags"
      tagGroups={TAG_GROUPS}
      tagLabels={TAG_LABELS}
      osmPoi={OSM_CONFIGS}
      initialSearch={initialSearch}
    />
  )
}
