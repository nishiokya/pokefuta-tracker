import type { PokefutaRecord, ManholeTitlesJson, SemanticPatch } from '../../semantic/semanticPatch'

type Props = {
  records: PokefutaRecord[]
  titles: ManholeTitlesJson
  onSave: (patch: SemanticPatch) => Promise<void>
  saving: boolean
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function AssignStationTagsTask(_props: Props) {
  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>駅近・駅構内タグを付ける</h2>
      <div style={{
        border: '2px dashed #d1d5db',
        borderRadius: 8,
        padding: 40,
        textAlign: 'center',
        color: '#6b7280',
      }}>
        <p style={{ fontSize: 18, marginBottom: 8 }}>🚉 実装予定</p>
        <p style={{ fontSize: 14 }}>
          駅近マンホールを検索・タグ付けする機能は将来実装予定です。
        </p>
        <p style={{ fontSize: 13, marginTop: 12 }}>
          対象タグ: <code>in_station</code> / <code>station_front</code> / <code>near_station</code> / <code>rail_access_good</code>
        </p>
        <p style={{ fontSize: 13, marginTop: 8, color: '#9ca3af' }}>
          将来的に Station Proximity Agent からの提案をレビューするUIをここに統合します。
        </p>
      </div>
    </div>
  )
}
