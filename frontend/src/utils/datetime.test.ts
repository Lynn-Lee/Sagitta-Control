import { describe, expect, it } from 'vitest'
import { formatDateTime } from './datetime'

describe('formatDateTime', () => {
  it('formats date-time strings as YYYY-MM-DD HH:mm:ss', () => {
    expect(formatDateTime('2026-06-02T22:32:33.987+08:00')).toBe('2026-06-02 22:32:33')
    expect(formatDateTime('2026/06/02 22:32:33')).toBe('2026-06-02 22:32:33')
  })

  it('pads date-only values with midnight time', () => {
    expect(formatDateTime('2026-06-02')).toBe('2026-06-02 00:00:00')
  })

  it('returns fallback for empty or invalid values', () => {
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime(undefined, '-')).toBe('-')
    expect(formatDateTime('not a date', '暂无数据')).toBe('暂无数据')
  })
})
