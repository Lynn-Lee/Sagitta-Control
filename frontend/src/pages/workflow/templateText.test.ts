import { describe, expect, it } from 'vitest'

import { normalizeTemplateText } from './templateText'

describe('normalizeTemplateText', () => {
  it('将字面 \\r\\n / \\n / \\t 还原为真实换行与制表符', () => {
    expect(normalizeTemplateText('a\\r\\nb')).toBe('a\nb')
    expect(normalizeTemplateText('a\\nb')).toBe('a\nb')
    expect(normalizeTemplateText('a\\tb')).toBe('a\tb')
  })

  it('空值返回空字符串', () => {
    expect(normalizeTemplateText(undefined)).toBe('')
    expect(normalizeTemplateText(null)).toBe('')
    expect(normalizeTemplateText('')).toBe('')
  })

  it('不含转义序列的文本原样返回', () => {
    expect(normalizeTemplateText('select 1')).toBe('select 1')
  })
})
