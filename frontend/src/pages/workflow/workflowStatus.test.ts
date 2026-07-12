import { describe, expect, it } from 'vitest'

import { STATUS_COLOR } from './workflowStatus'

describe('STATUS_COLOR', () => {
  it('覆盖 0-8 全部状态码且均为字符串颜色', () => {
    for (let s = 0; s <= 8; s++) {
      expect(typeof STATUS_COLOR[s]).toBe('string')
    }
  })

  it('关键状态映射正确', () => {
    expect(STATUS_COLOR[0]).toBe('processing')
    expect(STATUS_COLOR[1]).toBe('error')
    expect(STATUS_COLOR[2]).toBe('success')
    expect(STATUS_COLOR[3]).toBe('warning')
  })
})
