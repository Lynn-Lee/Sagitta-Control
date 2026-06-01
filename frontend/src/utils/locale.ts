import type { Locale } from 'antd/es/locale'
import zhCN from 'antd/es/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

dayjs.locale('zh-cn')

const datePickerLocale = zhCN.DatePicker!
const datePickerLang = datePickerLocale.lang

export const zhCNValidateMessages = zhCN.Form?.defaultValidateMessages ?? {
  required: '请输入${label}',
}

export const appLocale: Locale = {
  ...zhCN,
  locale: 'zh-cn',
  Calendar: {
    ...datePickerLocale,
    lang: {
      ...datePickerLang,
      locale: 'zh_CN',
      placeholder: '请选择日期',
      yearPlaceholder: '请选择年份',
      quarterPlaceholder: '请选择季度',
      monthPlaceholder: '请选择月份',
      weekPlaceholder: '请选择周',
      rangePlaceholder: ['开始日期', '结束日期'],
      rangeYearPlaceholder: ['开始年份', '结束年份'],
      rangeMonthPlaceholder: ['开始月份', '结束月份'],
      rangeQuarterPlaceholder: ['开始季度', '结束季度'],
      rangeWeekPlaceholder: ['开始周', '结束周'],
    },
  },
  DatePicker: {
    ...datePickerLocale,
    lang: {
      ...datePickerLang,
      locale: 'zh_CN',
      placeholder: '请选择日期',
      yearPlaceholder: '请选择年份',
      quarterPlaceholder: '请选择季度',
      monthPlaceholder: '请选择月份',
      weekPlaceholder: '请选择周',
      rangePlaceholder: ['开始日期', '结束日期'],
      rangeYearPlaceholder: ['开始年份', '结束年份'],
      rangeMonthPlaceholder: ['开始月份', '结束月份'],
      rangeQuarterPlaceholder: ['开始季度', '结束季度'],
      rangeWeekPlaceholder: ['开始周', '结束周'],
    },
  },
  Pagination: {
    ...zhCN.Pagination,
    items_per_page: '条/页',
  },
}
