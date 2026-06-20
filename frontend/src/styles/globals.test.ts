import { describe, expect, it } from 'vitest'
import globalsCss from './globals.css?raw'

describe('global menu styles', () => {
  it('keeps menu icon and text spacing at 10px', () => {
    expect(globalsCss).toMatch(
      /\.ant-menu-item-icon\s*\+\s*span,\s*\.anticon\s*\+\s*\.ant-menu-title-content\s*{[^}]*margin-inline-start:\s*10px\s*!important;/s,
    )
  })
})
