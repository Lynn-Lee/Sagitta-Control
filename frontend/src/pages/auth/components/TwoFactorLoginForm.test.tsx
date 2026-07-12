import { render, screen, waitFor } from '@testing-library/react'
import { fireEvent } from '@testing-library/dom'
import { describe, expect, it, vi } from 'vitest'

import { TwoFactorLoginForm } from './TwoFactorLoginForm'

const baseProps = {
  pendingUsername: 'alice',
  loading: false,
  onSubmit: vi.fn(),
  onBack: vi.fn(),
}

describe('TwoFactorLoginForm', () => {
  it('渲染二步验证提示（含账号）与两个操作按钮', () => {
    render(<TwoFactorLoginForm {...baseProps} />)
    expect(screen.getByText('需要完成二步验证')).toBeInTheDocument()
    expect(screen.getByText(/账号 alice 已开启 TOTP/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /验证并登录/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /返回登录/ })).toBeInTheDocument()
  })

  it('点击返回登录触发 onBack', () => {
    const onBack = vi.fn()
    render(<TwoFactorLoginForm {...baseProps} onBack={onBack} />)
    fireEvent.click(screen.getByRole('button', { name: /返回登录/ }))
    expect(onBack).toHaveBeenCalledTimes(1)
  })

  it('输入合法 6 位验证码并提交触发 onSubmit', async () => {
    const onSubmit = vi.fn()
    render(<TwoFactorLoginForm {...baseProps} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByPlaceholderText('请输入 6 位验证码'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: /验证并登录/ }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ totp_code: '123456' }))
  })
})
