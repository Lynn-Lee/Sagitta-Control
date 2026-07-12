import { describe, expect, it } from 'vitest'

import { RISK_LEVEL_META, resolveRiskMeta } from './riskLevel'

describe('resolveRiskMeta', () => {
  it('已知等级取标准元数据', () => {
    expect(resolveRiskMeta('high')).toEqual(RISK_LEVEL_META.high)
    expect(resolveRiskMeta('medium')).toEqual(RISK_LEVEL_META.medium)
    expect(resolveRiskMeta('low')).toEqual(RISK_LEVEL_META.low)
  })

  it('未知或缺省等级回落到低风险（与原三元判断 else 分支等价）', () => {
    expect(resolveRiskMeta('unknown')).toEqual(RISK_LEVEL_META.low)
    expect(resolveRiskMeta(undefined)).toEqual(RISK_LEVEL_META.low)
    expect(resolveRiskMeta('')).toEqual(RISK_LEVEL_META.low)
  })

  it('高风险映射到 error/高风险，中风险到 warning，低风险到 success', () => {
    expect(RISK_LEVEL_META.high).toEqual({ label: '高风险', color: 'error', alertType: 'error' })
    expect(RISK_LEVEL_META.medium.color).toBe('warning')
    expect(RISK_LEVEL_META.low.color).toBe('success')
  })
})
