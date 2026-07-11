import { describe, expect, it } from 'vitest'

import { extractFileName } from './userImportExport'

describe('extractFileName', () => {
  it('优先解析 RFC 5987 UTF-8 编码文件名并解码', () => {
    const header = "attachment; filename*=UTF-8''%E7%94%A8%E6%88%B7.xlsx"
    expect(extractFileName(header)).toBe('用户.xlsx')
  })

  it('回退解析普通带引号 filename', () => {
    expect(extractFileName('attachment; filename="users_export.csv"')).toBe('users_export.csv')
  })

  it('解析无引号 filename', () => {
    expect(extractFileName('attachment; filename=users.xlsx')).toBe('users.xlsx')
  })

  it('缺省或无法解析时返回 fallback', () => {
    expect(extractFileName(undefined)).toBe('users_export.xlsx')
    expect(extractFileName('attachment', 'template.csv')).toBe('template.csv')
  })
})
