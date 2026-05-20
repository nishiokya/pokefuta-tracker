import type { ManholeTitlesJson, SemanticPatch } from '../semantic/semanticPatch'
import { applyPatch, serializeTitles } from '../semantic/semanticPatchApplier'

export { normCity } from '../semantic/semanticPatchApplier'

export async function loadTitles(): Promise<ManholeTitlesJson> {
  const res = await fetch('/__editor/data/titles')
  if (!res.ok) throw new Error(`Failed to load titles: ${res.status}`)
  return res.json()
}

export async function loadSessionPatches(): Promise<SemanticPatch[]> {
  const res = await fetch('/__editor/workspace/patches')
  if (!res.ok) throw new Error(`Failed to load patches: ${res.status}`)
  return res.json()
}

export async function savePatch(
  patch: SemanticPatch,
  currentTitles: ManholeTitlesJson
): Promise<ManholeTitlesJson> {
  const updated = applyPatch(currentTitles, patch)
  await writeTitles(updated)
  await logPatch(patch)
  return updated
}

export async function savePatches(
  patches: SemanticPatch[],
  currentTitles: ManholeTitlesJson
): Promise<ManholeTitlesJson> {
  let updated = currentTitles
  for (const patch of patches) {
    updated = applyPatch(updated, patch)
  }
  await writeTitles(updated)
  for (const patch of patches) {
    await logPatch(patch)
  }
  return updated
}

async function writeTitles(titles: ManholeTitlesJson): Promise<void> {
  const serialized = serializeTitles(titles)
  const res = await fetch('/__editor/data/titles', {
    method: 'POST',
    body: serialized,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  })
  if (!res.ok) throw new Error(`Failed to save titles: ${res.status}`)
}

async function logPatch(patch: SemanticPatch): Promise<void> {
  const res = await fetch('/__editor/workspace/patches', {
    method: 'POST',
    body: JSON.stringify(patch),
    headers: { 'Content-Type': 'application/json' },
  })
  if (!res.ok) throw new Error(`Failed to log patch: ${res.status}`)
}

export async function clearSessionPatches(): Promise<void> {
  const res = await fetch('/__editor/workspace/patches', { method: 'DELETE' })
  if (!res.ok) throw new Error(`Failed to clear patches: ${res.status}`)
}
