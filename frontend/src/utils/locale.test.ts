import dayjs from 'dayjs'
import { describe, expect, it } from 'vitest'

import { appLocale } from './locale'

describe('appLocale', () => {
  it('keeps Ant Design date pickers in Simplified Chinese', () => {
    expect(dayjs.locale()).toBe('zh-cn')
    expect(appLocale.locale).toBe('zh-cn')
    expect(appLocale.DatePicker?.lang?.locale).toBe('zh_CN')
    expect(appLocale.DatePicker?.lang?.placeholder).toBe('请选择日期')
    expect(appLocale.DatePicker?.lang?.rangePlaceholder).toEqual(['开始日期', '结束日期'])
    expect(appLocale.DatePicker?.lang?.today).toBe('今天')
  })
})
