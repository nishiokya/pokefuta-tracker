import type { PokefutaRecord, ManholeTitlesJson, SemanticPatch, ManholeEntry } from '../../semantic/semanticPatch'
import { MapTagsTask } from '../shared/MapTagsTask'

const STATION_TAGS = ['in_station', 'station_front', 'near_station', 'rail_access_good'] as const

const TAG_LABEL: Record<(typeof STATION_TAGS)[number], string> = {
  in_station: '🚉 駅構内',
  station_front: '🏢 駅前',
  near_station: '🚶 駅近',
  rail_access_good: '🚆 アクセス良',
}

function stationHint(r: PokefutaRecord, entry: ManholeEntry | undefined): boolean {
  return (
    r.address.includes('駅') ||
    (entry?.building ?? '').includes('駅') ||
    (entry?.place_detail ?? '').includes('駅')
  )
}

type Props = {
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSaveMany: (patches: SemanticPatch[]) => Promise<void>
  saving: boolean
}

export function AssignStationTagsTask(props: Props) {
  return (
    <MapTagsTask
      {...props}
      title="駅近・駅構内タグを付ける"
      taskType="assign_station_tags"
      tags={STATION_TAGS}
      tagLabels={TAG_LABEL}
      hintFilter={{ label: '駅キーワードのみ', fn: stationHint, defaultOn: true }}
    />
  )
}
