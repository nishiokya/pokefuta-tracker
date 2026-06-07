import type { PokefutaRecord, ManholeTitlesJson, SemanticPatch } from '../../semantic/semanticPatch'
import { MapTagsTask } from '../shared/MapTagsTask'
import type { OsmPoiConfig } from '../shared/MapTagsTask'

const OSM_CONFIGS: OsmPoiConfig[] = [
  { type: 'museum', label: '博物館', defaultTag: 'museum', radiusM: 100 },
  { type: 'park', label: '公園', defaultTag: 'park', radiusM: 100 },
]


const TOURISM_TAGS = ['tourism', 'park', 'museum', 'history', 'food', 'world_heritage'] as const

const TAG_LABEL: Record<(typeof TOURISM_TAGS)[number], string> = {
  tourism: '🗺 観光',
  park: '🌳 公園',
  museum: '🏛 博物館',
  history: '🏯 歴史',
  food: '🍜 グルメ',
  world_heritage: '🏯 世界遺産',
}

type Props = {
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSaveMany: (patches: SemanticPatch[]) => Promise<void>
  saving: boolean
}

export function AssignTourismTagsTask(props: Props) {
  return (
    <MapTagsTask
      {...props}
      title="観光地タグを付ける"
      taskType="assign_tourism_tags"
      tags={TOURISM_TAGS}
      tagLabels={TAG_LABEL}
      osmPoi={OSM_CONFIGS}
    />
  )
}
