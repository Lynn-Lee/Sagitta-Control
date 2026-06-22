import type { ReactElement } from 'react'
import { describe, expect, it } from 'vitest'

import { TruncatedCell } from './TruncatedCell'
import { renderTruncatedCell } from './renderTruncatedCell'

describe('renderTruncatedCell', () => {
  it('ignores Ant Design table record argument when creating tooltip text', () => {
    const record = { detail: '撤销查询权限 #2，用户ID=13，实例ID=2，库=test，表=codex_e2e_20260609173455' }
    const element = renderTruncatedCell(record.detail, record) as ReactElement<{
      value: unknown
      tooltipValue?: unknown
    }>

    expect(element.type).toBe(TruncatedCell)
    expect(element.props.value).toBe(record.detail)
    expect(element.props).not.toHaveProperty('tooltipValue')
  })
})
