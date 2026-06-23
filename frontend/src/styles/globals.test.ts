import { describe, expect, it } from 'vitest'
import globalsCss from './globals.css?raw'

describe('global menu styles', () => {
  it('keeps root menu items visually stronger than submenu items', () => {
    expect(globalsCss).toMatch(
      /\.ant-menu\.ant-menu-root\s*>\s*\.ant-menu-item,\s*\.ant-menu\.ant-menu-root\s*>\s*\.ant-menu-submenu\s*>\s*\.ant-menu-submenu-title\s*{[^}]*font-size:\s*14px\s*!important;[^}]*font-weight:\s*700\s*!important;/s,
    )
  })

  it('keeps menu icon and text spacing at 10px', () => {
    expect(globalsCss).toMatch(
      /\.ant-menu-item-icon\s*\+\s*span,\s*\.anticon\s*\+\s*\.ant-menu-title-content\s*{[^}]*margin-inline-start:\s*10px\s*!important;/s,
    )
  })
})
