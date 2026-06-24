import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import CommercialOpsPage from './CommercialOpsPage'

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

vi.mock('@/api/commercial', () => ({
  commercialApi: {
    onboardingStatus: vi.fn().mockResolvedValue({
      steps: [],
      next_actions: [],
      risk_items: [],
      completed_count: 0,
      total: 0,
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
    completeStep: vi.fn(),
    bootstrapTrial: vi.fn(),
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
})
