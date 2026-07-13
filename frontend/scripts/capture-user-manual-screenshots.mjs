import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { validateScreenshotCaptureConfig } from './capture-user-manual-screenshots.config.mjs'

const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const username = process.env.E2E_USERNAME || ''
const password = process.env.E2E_PASSWORD || ''
const outputDir = resolve(process.env.E2E_SCREENSHOT_DIR || '../docs/screenshots/user-manual')
const smokeOnly = process.env.E2E_SMOKE_ONLY === 'true'
const chromiumExecutablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined

validateScreenshotCaptureConfig({ username, password, smokeOnly })

const pages = [
  ['01-login.png', '/login', '登录页'],
  ['02-dashboard-query.png', '/dashboard/query', '在线查询概览'],
  ['03-dashboard-workflow.png', '/dashboard/workflow', 'SQL 工单概览'],
  ['04-dashboard-archive.png', '/dashboard/archive', '数据归档概览'],
  ['05-dashboard-instance.png', '/dashboard/instance', '实例与库概览'],
  ['06-workflow-list.png', '/workflow', 'SQL 工单列表'],
  ['07-workflow-submit.png', '/workflow/submit', 'SQL 工单提交页'],
  ['08-workflow-templates.png', '/workflow/templates', '工单模板页面'],
  ['09-query-workbench.png', '/query', '在线查询工作台'],
  ['10-query-privileges.png', '/query/privileges', '查询权限申请页'],
  ['11-query-history.png', '/query/history', '查询历史页面'],
  ['12-monitor.png', '/monitor', '观测中心实例总览'],
  ['12-monitor-diagnostics.png', '/monitor/diagnostics', '实例诊断概览'],
  ['12-monitor-sql-insight.png', '/monitor/diagnostics?view=sql', 'SQL 洞察页面'],
  ['13-archive.png', '/archive', '数据归档页面'],
  ['14-data-dictionary.png', '/schema', '数据字典页面'],
  ['15-instance-management.png', '/instance', '实例管理页面'],
  ['16-user-management.png', '/system/users', '用户管理页面'],
  ['17-resource-groups.png', '/system/groups', '资源组管理页面'],
  ['18-role-management.png', '/system/roles', '角色管理页面'],
  ['19-user-groups.png', '/system/user-groups', '用户组管理页面'],
  ['20-approval-flows.png', '/system/approval-flows', '审批流管理页面'],
  ['21-system-config.png', '/system/config', '系统配置页面'],
  ['22-masking-rules.png', '/masking', '脱敏规则页面'],
  ['23-commercial-support.png', '/commercial', '交付与支持页面'],
  ['24-audit-log.png', '/audit', '审计日志页面'],
]

function url(path) {
  return new URL(path, baseUrl).toString()
}

async function waitForStablePage(page) {
  await page.waitForLoadState('domcontentloaded')
  await page.waitForTimeout(500)
  await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {})
}

async function login(page) {
  await page.goto(url('/login'))
  await waitForStablePage(page)
  if (!username || !password) {
    console.log('No E2E_USERNAME/E2E_PASSWORD supplied; authenticated pages will verify redirect behavior only.')
    return false
  }
  await page.getByPlaceholder('用户名').fill(username)
  await page.getByPlaceholder('密码').fill(password)
  const submitButton = page.locator('.sagitta-auth-form button[type="submit"]')
  await submitButton.click()
  await page.waitForURL((u) => !u.pathname.endsWith('/login'), { timeout: 15000 }).catch(() => {})
  await waitForStablePage(page)
  const current = page.url()
  if (current.includes('/login')) {
    throw new Error('Login did not leave /login. Check credentials, forced password change, or 2FA.')
  }
  return true
}

async function applyOverviewRange(page) {
  // 概览类页面的时间范围默认 7 天，统一改为 60 天以展示更完整的趋势数据。
  const inputs = page.locator('.overview-range-days-input input')
  const count = await inputs.count().catch(() => 0)
  for (let i = 0; i < count; i += 1) {
    await inputs.nth(i).fill('60').catch(() => {})
    await inputs.nth(i).press('Enter').catch(() => {})
  }
  if (count) {
    await page.waitForTimeout(800)
    await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {})
  }
}

async function dismissPasswordBanner(page) {
  // 移除账号相关的“密码即将到期”提醒，避免污染产品截图。
  await page
    .evaluate(() => {
      document.querySelectorAll('.ant-alert').forEach((el) => {
        if (el.textContent && el.textContent.includes('密码即将到期')) el.remove()
      })
    })
    .catch(() => {})
}

async function capture(page, fileName, path, label) {
  await page.goto(url(path))
  await waitForStablePage(page)
  const title = await page.locator('body').innerText({ timeout: 5000 }).catch(() => '')
  if (!title.trim()) throw new Error(`${label} rendered empty body`)
  if (!smokeOnly) {
    await applyOverviewRange(page)
    await dismissPasswordBanner(page)
    await page.mouse.move(0, 0) // 清除图表 hover tooltip，避免污染截图
    await page.waitForTimeout(200)
    await page.screenshot({ path: resolve(outputDir, fileName), fullPage: true })
  }
  console.log(`[PASS] ${label}: ${path}`)
}

mkdirSync(outputDir, { recursive: true })

const { chromium } = await import('@playwright/test')
const browser = await chromium.launch(chromiumExecutablePath ? { executablePath: chromiumExecutablePath } : undefined)
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 })

try {
  await capture(page, ...pages[0])
  const authed = await login(page)
  for (const item of pages.slice(1)) {
    await capture(page, ...item)
    if (!authed && !page.url().includes('/login')) {
      throw new Error(`${item[2]} should redirect to /login without credentials`)
    }
  }
  console.log(smokeOnly ? 'Frontend smoke E2E passed.' : `Screenshots written to ${outputDir}`)
} finally {
  await browser.close()
}
