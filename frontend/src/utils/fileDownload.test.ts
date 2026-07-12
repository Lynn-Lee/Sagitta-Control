import { describe, expect, it } from 'vitest'

import { extractFileName } from './fileDownload'

describe('extractFileName', () => {
  it('优先解析 RFC 5987 UTF-8 编码文件名并解码', () => {
    const header = "attachment; filename*=UTF-8''%E7%94%A8%E6%88%B7%E7%BB%84.xlsx"
    expect(extractFileName(header)).toBe('用户组.xlsx')
  })

  it('回退解析普通带引号 filename', () => {
    expect(extractFileName('attachment; filename="export.csv"')).toBe('export.csv')
  })

  it('解析无引号 filename', () => {
    expect(extractFileName('attachment; filename=data.xlsx')).toBe('data.xlsx')
  })

  it('缺省时返回通用 fallback', () => {
    expect(extractFileName(undefined)).toBe('download')
  })

  it('无法解析时返回传入的 fallback', () => {
    expect(extractFileName('attachment', 'template.csv')).toBe('template.csv')
  })
})
