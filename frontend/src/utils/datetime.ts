export function formatDateTime(value?: string | null, fallback = '—') {
  if (!value) return fallback
  return value
    .replace('T', ' ')
    .replace(/\.\d+/, '')
    .replace(/Z$/, '')
    .replace(/[+-]\d{2}:?\d{2}$/, '')
    .slice(0, 19)
}
