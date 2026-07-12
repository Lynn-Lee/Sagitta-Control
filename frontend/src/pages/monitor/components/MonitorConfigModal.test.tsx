import { render, screen } from '@testing-library/react'
import { fireEvent } from '@testing-library/dom'
import { Form } from 'antd'
import { describe, expect, it, vi } from 'vitest'

import { MonitorConfigModal } from './MonitorConfigModal'

type HarnessProps = Omit<Parameters<typeof MonitorConfigModal>[0], 'form'>

function Harness(props: HarnessProps) {
  const [form] = Form.useForm()
  return <MonitorConfigModal form={form} {...props} />
}

const baseProps: HarnessProps = {
  open: true,
  scope: 'single',
  targetName: 'inst-1',
  instancesCount: 3,
  isSaving: false,
  onOk: vi.fn(),
  onClose: vi.fn(),
}

describe('MonitorConfigModal', () => {
  it('单实例态渲染实例名标题与三档采集页签', () => {
    render(<Harness {...baseProps} />)
    expect(screen.getByText('统一采集配置 - inst-1')).toBeInTheDocument()
    expect(screen.getByText('原生监控')).toBeInTheDocument()
    expect(screen.getByText('会话采集')).toBeInTheDocument()
    expect(screen.getByText('SQL 采集')).toBeInTheDocument()
    expect(screen.getByText('该配置仅作用于当前实例')).toBeInTheDocument()
  })

  it('全部实例态标题与描述含实例数', () => {
    render(<Harness {...baseProps} scope="all" />)
    expect(screen.getByText('统一采集配置 - 全部实例')).toBeInTheDocument()
    expect(screen.getByText(/为当前列表中的 3 个实例写入相同采集配置/)).toBeInTheDocument()
  })

  it('保存 / 取消按钮分别触发 onOk / onClose', () => {
    const onOk = vi.fn()
    const onClose = vi.fn()
    render(<Harness {...baseProps} onOk={onOk} onClose={onClose} />)
    // antd 会在两个中文字符间插入空格（保存 → 保 存），故用空白容忍的正则匹配。
    fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }))
    fireEvent.click(screen.getByRole('button', { name: /取\s*消/ }))
    expect(onOk).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
