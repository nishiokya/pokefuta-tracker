import type { PokefutaRecord, ManholeTitlesJson, SemanticPatch } from '../../semantic/semanticPatch'
import { MapTagsTask } from '../shared/MapTagsTask'

const LOCATION_TAGS = ['seaside', 'beach', 'lakeside', 'river', 'remote_island'] as const

const TAG_LABEL: Record<(typeof LOCATION_TAGS)[number], string> = {
  seaside: '🌊 海沿い',
  beach: '🏖 ビーチ',
  lakeside: '🏞 湖畔',
  river: '🌊 川沿い',
  remote_island: '🏝 離島',
}

type Props = {
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSaveMany: (patches: SemanticPatch[]) => Promise<void>
  saving: boolean
}

export function AssignLocationTagsTask(props: Props) {
  return (
    <MapTagsTask
      {...props}
      title="海・湖・離島タグを付ける"
      taskType="assign_location_tags"
      tags={LOCATION_TAGS}
      tagLabels={TAG_LABEL}
    />
  )
}
