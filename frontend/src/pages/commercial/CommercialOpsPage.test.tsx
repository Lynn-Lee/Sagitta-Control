import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CommercialOpsPage from './CommercialOpsPage'
import { commercialApi } from '@/api/commercial'

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}))

const { alertEvent } = vi.hoisted(() => ({
  alertEvent: {
    id: 1,
    instance_id: 16,
    instance_name: 'PostgreSQL16-Test-Primary-With-Long-Name',
    db_type: 'postgresql',
    rule_key: 'connection_usage',
    severity: 'warning',
    status: 'resolved',
    title: '连接使用率告警',
    message: 'connection_usage 当前值 0.85，触发条件 >= 0.8',
    metric_value: 0.85,
    threshold: 0.8,
    last_seen_at: '2026-06-24T06:44:16',
  },
}))

const { onboardingStep, onboardingComplete } = vi.hoisted(() => ({
  onboardingStep: {
    key: 'governance',
    label: '治理模板',
    path: '/system/groups',
    completed: false,
    auto_detected: false,
    status: 'blocked',
    category: '治理模板',
    required: true,
    reason: '请完成资源组、用户组和审批流配置',
    evidence: '资源组、用户组或审批流尚未齐备',
    suggested_action: '确认资源组、用户组和审批流已经覆盖首个实例和试用管理员。',
    action_label: '初始化模板',
    quick_action: 'trial_bootstrap',
    can_auto_fix: true,
  },
  onboardingComplete: {
    key: 'governance',
    label: '治理模板',
    path: '/system/groups',
    completed: true,
    auto_detected: false,
    status: 'done',
    category: '治理模板',
    required: true,
    reason: '已手动确认治理模板',
    evidence: '已手动确认',
    suggested_action: '确认资源组、用户组和审批流已经覆盖首个实例和试用管理员。',
    action_label: '初始化模板',
    quick_action: 'trial_bootstrap',
    can_auto_fix: true,
  },
}))

vi.mock('@/api/commercial', () => ({
  commercialApi: {
    onboardingStatus: vi.fn().mockResolvedValue({
      steps: [onboardingStep],
      next_actions: [onboardingStep],
      risk_items: [onboardingStep],
      completed_count: 0,
      total: 1,
      is_complete: false,
    }),
    engineMatrix: vi.fn().mockResolvedValue({ items: [], capability_labels: {} }),
    alertEvents: vi.fn().mockResolvedValue({ total: 1, items: [alertEvent] }),
    supportAbout: vi.fn().mockResolvedValue({
      version: '2.3.0',
      deployment_mode: 'source-test',
      project: 'Sagitta Control',
      project_code: 'sagitta-control',
      deployment_fingerprint: 'fingerprint',
      license: {
        status: 'trial',
        reason: '',
        is_trial: true,
        customer_id: 'customer',
        activation_customer_id: 'customer',
        activation_deployment_fingerprint: 'fingerprint',
        company_name: '测试客户',
        expires_at: null,
        days_remaining: 7,
      },
      usage: {
        active_users: 1,
        active_instances: 1,
        db_type_distribution: {},
      },
      runtime: {
        health: 'ok',
        app_env: 'test',
        deployment_mode: 'source-test',
        failed_monitor_collect_configs: 0,
      },
      readiness: {
        status: 'ready',
        conclusion: '可推广',
        summary: '测试环境就绪',
        score: 100,
        checks: [],
        action_items: [],
      },
      docs: [],
      support: { email: 'support@example.com', license_server: 'https://license.example.com' },
    }),
    retentionPolicy: vi.fn().mockResolvedValue({ items: [] }),
    completeStep: vi.fn().mockResolvedValue({
      steps: [onboardingComplete],
      next_actions: [],
      risk_items: [],
      completed_count: 1,
      total: 1,
      is_complete: true,
    }),
    bootstrapTrial: vi.fn().mockResolvedValue({
      status: 'success',
      created: ['用户试用资源组'],
      updated: [],
      skipped: [],
      acceptance_run: { id: 88 },
      onboarding: {
        steps: [onboardingComplete],
        next_actions: [],
        risk_items: [],
        completed_count: 1,
        total: 1,
        is_complete: true,
      },
      readiness: { status: 'ready', conclusion: '可推广', summary: 'ok', score: 100, checks: [], action_items: [] },
    }),
    createAcceptanceRun: vi.fn(),
    createDiagnosticBundle: vi.fn(),
    complianceReport: vi.fn(),
    updateRetentionPolicy: vi.fn(),
    cleanupRetention: vi.fn(),
    ackAlert: vi.fn(),
    silenceAlert: vi.fn(),
    resolveAlert: vi.fn(),
    closeAlert: vi.fn(),
    downloadFile: vi.fn(),
  },
}))

describe('CommercialOpsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('keeps alert text columns truncated while showing last trigger time in full', async () => {
    render(<CommercialOpsPage />)

    await waitFor(() => expect(screen.getByText('告警中心')).toBeInTheDocument())
    fireEvent.click(screen.getByText('告警中心'))

    const instanceCell = await screen.findByText(alertEvent.instance_name)
    const ruleCell = screen.getByText(alertEvent.rule_key)
    const messageCell = screen.getByText(alertEvent.message)
    const lastSeenCell = screen.getByText('2026-06-24 06:44:16')

    expect(instanceCell.closest('.sagitta-table-truncated-cell')).toBeInTheDocument()
    expect(ruleCell.closest('.sagitta-table-truncated-cell')).toBeInTheDocument()
    expect(messageCell.closest('.sagitta-table-truncated-cell')).toBeInTheDocument()
    expect(lastSeenCell.closest('.sagitta-table-truncated-cell')).not.toBeInTheDocument()
    expect(lastSeenCell).toHaveAttribute('style', expect.stringContaining('white-space: nowrap'))
  })

  it('runs onboarding quick actions and manual completion from the implementation table', async () => {
    render(<CommercialOpsPage />)

    expect((await screen.findAllByText('治理模板')).length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: /初始化模板/ }))

    await waitFor(() => expect(commercialApi.bootstrapTrial).toHaveBeenCalledTimes(1))
    expect(await screen.findByText(/新增 1 项，更新 0 项，跳过 0 项/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /手动完成/ }))

    await waitFor(() => expect(commercialApi.completeStep).toHaveBeenCalledWith('governance'))
  })

  it('dispatches alert close action and refreshes alert rows', async () => {
    vi.mocked(commercialApi.alertEvents)
      .mockResolvedValueOnce({ total: 1, items: [{ ...alertEvent, status: 'firing' }] })
      .mockResolvedValueOnce({ total: 0, items: [] })

    render(<CommercialOpsPage />)

    await waitFor(() => expect(screen.getByText('告警中心')).toBeInTheDocument())
    fireEvent.click(screen.getByText('告警中心'))
    fireEvent.click(await screen.findByRole('button', { name: /关闭/ }))

    await waitFor(() => expect(commercialApi.closeAlert).toHaveBeenCalledWith(1, '交付与支持页面关闭'))
    expect(commercialApi.alertEvents).toHaveBeenLastCalledWith({ page_size: 50 })
  })
})
