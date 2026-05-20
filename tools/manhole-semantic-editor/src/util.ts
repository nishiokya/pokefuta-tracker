let counter = 0

export function newPatchId(): string {
  return `${Date.now()}-${++counter}`
}

export function todayJST(): string {
  const now = new Date()
  const jst = new Date(now.getTime() + 9 * 60 * 60 * 1000)
  return jst.toISOString().slice(0, 10)
}
