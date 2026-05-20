import type { PokefutaRecord } from '../semantic/semanticPatch'

export async function loadPokefutaRecords(): Promise<PokefutaRecord[]> {
  const res = await fetch('/__editor/data/ndjson')
  if (!res.ok) throw new Error(`Failed to load ndjson: ${res.status}`)
  return res.json()
}
