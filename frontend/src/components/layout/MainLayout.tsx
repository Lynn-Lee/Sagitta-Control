import { useEffect, useMemo, useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Avatar, Dropdown, Space, Typography, Badge, Button, Tooltip, Drawer, Grid } from 'antd'
import type { MenuProps } from 'antd'
import {
  DashboardOutlined, FileTextOutlined, SearchOutlined, MonitorOutlined,
  DatabaseOutlined, SettingOutlined, AuditOutlined, BellOutlined,
  LogoutOutlined, UserOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  SlidersFilled, BugOutlined, ThunderboltOutlined, SafetyCertificateOutlined,
  KeyOutlined, EyeInvisibleOutlined, ApartmentOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '@/store/auth'

const { Header, Sider, Content } = Layout
const { Text } = Typography
const { useBreakpoint } = Grid

// SagittaDB Logo SVG
const SagittaLogo = ({ size = 28, color = '#165DFF' }: { size?: number; color?: string }) => (
  <svg viewBox="0 0 32 32" fill="none" width={size} height={size}>
    <path d="M16 2L30 10V22L16 30L2 22V10L16 2Z" fill={color} />
    <path d="M10 14L16 8L22 14" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    <line x1="16" y1="8" x2="16" y2="24" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
    <path d="M11 19H21" stroke="white" strokeWidth="2" strokeLinecap="round" />
    <path d="M12 22H20" stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.55" />
  </svg>
)

type NavItem = NonNullable<MenuProps['items']>[number] & {
  permission?: string
  children?: NavItem[]
}

const NAV_ITEMS: NavItem[] = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: 'Dashboard', permission: 'menu_dashboard' },
  {
    key: 'workflow-group', icon: <FileTextOutlined />, label: 'SQL 工单', permission: 'menu_sqlworkflow',
    children: [
      { key: '/workflow', label: '工单列表' },
      { key: '/workflow/submit', label: '提交工单' },
      { key: '/workflow/templates', label: '工单模板' },
    ],
  },
  {
    key: 'query-group', icon: <SearchOutlined />, label: '在线查询', permission: 'menu_query',
    children: [
      { key: '/query', label: '执行查询' },
      { key: '/query/privileges', label: '查询权限' },
    ],
  },
  { key: '/monitor', icon: <MonitorOutlined />, label: '可观测中心', permission: 'menu_monitor' },
  {
    key: 'ops-group', icon: <SlidersFilled />, label: '运维工具', permission: 'menu_ops',
    children: [
      { key: '/diagnostic', icon: <BugOutlined />, label: '会话管理' },
      { key: '/slowlog', label: '慢日志分析' },
      { key: '/optimize', icon: <ThunderboltOutlined />, label: 'SQL 优化' },
      { key: '/schema', label: '数据字典' },
      { key: '/archive', label: '数据归档' },
      { key: '/binlog', label: '回滚辅助' },
    ],
  },
  { key: '/instance', icon: <DatabaseOutlined />, label: '实例管理', permission: 'instance_manage' },
  {
    key: 'system-group', icon: <SettingOutlined />, label: '系统管理', permission: 'menu_system',
    children: [
      { key: '/system/users', label: '用户管理' },
      { key: '/system/groups', label: '资源组管理' },
      { key: '/system/roles', icon: <SafetyCertificateOutlined />, label: '角色管理' },
      { key: '/system/user-groups', icon: <ApartmentOutlined />, label: '用户组管理' },
      { key: '/system/approval-flows', icon: <ApartmentOutlined />, label: '审批流管理' },
      { key: '/system/config', icon: <SafetyCertificateOutlined />, label: '系统配置' },
      { key: '/masking', icon: <EyeInvisibleOutlined />, label: '数据脱敏规则' },
    ],
  },
  { key: '/audit', icon: <AuditOutlined />, label: '审计日志', permission: 'menu_audit' },
]

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [menuOpenKeys, setMenuOpenKeys] = useState<string[]>([])
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const screens = useBreakpoint()
  const isMobile = !screens.lg

  const handleLogout = () => { logout(); navigate('/login') }

  const userMenuItems: MenuProps['items'] = [
    { key: 'profile', icon: <UserOutlined />, label: '个人设置', onClick: () => navigate('/profile') },
    { key: 'change-pw', icon: <KeyOutlined />, label: '修改密码', onClick: () => navigate('/profile') },
    { type: 'divider' },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true, onClick: handleLogout },
  ]

  const selectedMenuKey = useMemo(() => {
    const leafKeys = NAV_ITEMS.flatMap((item) => item.children?.map((child) => child.key as string) ?? [item.key as string])
      .filter((key) => !key.endsWith('-group'))
      .sort((a, b) => b.length - a.length)

    return leafKeys.find((key) => location.pathname === key || location.pathname.startsWith(`${key}/`)) || '/dashboard'
  }, [location.pathname])

  const selectedKeys = [selectedMenuKey]
  const visibleNavItems = NAV_ITEMS
    .filter((item) => !item.permission || hasPermission(item.permission))
    .map((item) => {
      if (!item.children) return item
      return {
        ...item,
        children: item.children.filter(Boolean),
      }
    })
  const openKeys = useMemo(() => {
    const parent = NAV_ITEMS.find((item) => item.children?.some((child) => child.key === selectedMenuKey))
    return parent ? [parent.key as string] : []
  }, [selectedMenuKey])
  const initials = (user?.display_name || user?.username || 'S')[0].toUpperCase()

  useEffect(() => {
    setMobileNavOpen(false)
  }, [location.pathname])

  useEffect(() => {
    setMenuOpenKeys(openKeys)
  }, [openKeys])

  const menuNode = (
    <Menu
      mode="inline"
      items={visibleNavItems}
      selectedKeys={selectedKeys}
      openKeys={menuOpenKeys}
      onOpenChange={(keys) => setMenuOpenKeys(keys as string[])}
      onClick={({ key }) => {
        navigate(key)
        if (isMobile) setMobileNavOpen(false)
      }}
      style={{
        border: 'none',
        paddingTop: 8,
        paddingBottom: 16,
        fontSize: 13,
      }}
    />
  )

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* ── Header ────────────────────────────────────────────── */}
      <Header style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 200,
        height: 56, padding: isMobile ? '0 12px 0 0' : '0 16px 0 0',
        background: '#0F172A',
        borderBottom: '1px solid rgba(22,93,255,0.12)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        {/* 左侧：折叠按钮 + Logo */}
        <Space size={0}>
          <Button type="text"
            icon={isMobile ? <MenuUnfoldOutlined /> : (collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />)}
            onClick={() => {
              if (isMobile) {
                setMobileNavOpen(true)
                return
              }
              setCollapsed(!collapsed)
            }}
            style={{ color: 'rgba(255,255,255,0.65)', width: 56, height: 56, borderRadius: 0 }}
          />
          <Space size={10} style={{ cursor: 'pointer' }} onClick={() => navigate('/dashboard')}>
            <SagittaLogo size={26} color="#165DFF" />
            <div style={{ lineHeight: 1 }}>
              <div style={{
                fontFamily: "'Inter', sans-serif",
                fontWeight: 800,
                fontSize: 15,
                color: '#FFFFFF',
                letterSpacing: '-0.3px',
              }}>
                SagittaDB
              </div>
              <div style={{
                fontFamily: "'Noto Sans SC', sans-serif",
                fontWeight: 400,
                fontSize: 10,
                color: 'rgba(22,93,255,0.8)',
                letterSpacing: '3px',
                marginTop: 1,
              }}>
                矢 准 数 据
              </div>
            </div>
          </Space>
        </Space>

        {/* 右侧：通知 + 用户 */}
        <Space size={4}>
          <Tooltip title="通知">
            <Badge count={0} size="small">
              <Button type="text" icon={<BellOutlined />}
                style={{ color: 'rgba(255,255,255,0.65)', borderRadius: 6 }} />
            </Badge>
          </Tooltip>
          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight" trigger={['click']}>
            <Space style={{ cursor: 'pointer', padding: '0 8px' }} size={8}>
              <Avatar size={28} style={{
                background: '#165DFF',
                fontSize: 12,
                fontFamily: "'Inter', sans-serif",
                fontWeight: 600,
              }}>
                {initials}
              </Avatar>
              {!isMobile && (
                <Text style={{
                  color: 'rgba(255,255,255,0.8)',
                  fontSize: 13,
                  fontFamily: "'Inter', sans-serif",
                  fontWeight: 500,
                  maxWidth: 160,
                }} ellipsis>
                  {user?.display_name || user?.username || '用户'}
                </Text>
              )}
            </Space>
          </Dropdown>
        </Space>
      </Header>

      <Layout style={{ marginTop: 56 }}>
        {!isMobile && (
          <Sider
            collapsible collapsed={collapsed} onCollapse={setCollapsed}
            theme="light" width={216}
            style={{
              position: 'fixed', left: 0, top: 56, bottom: 0,
              height: 'calc(100vh - 56px)',
              borderRight: '1px solid #E5E6EB',
              overflow: 'auto', zIndex: 100,
              background: '#FFFFFF',
            }}
            trigger={null}
          >
            {menuNode}
            {!collapsed && (
              <div style={{
                padding: '12px 16px',
                borderTop: '1px solid #F0F1F5',
                marginTop: 8,
              }}>
                <Text style={{
                  fontSize: 10,
                  fontFamily: "'JetBrains Mono', monospace",
                  color: '#C9CDD4',
                  letterSpacing: '0.5px',
                }}>
                  全引擎兼容 · 全流程可观测
                </Text>
              </div>
            )}
          </Sider>
        )}

        {isMobile && (
          <Drawer
            title="导航"
            placement="left"
            open={mobileNavOpen}
            onClose={() => setMobileNavOpen(false)}
            width={280}
            styles={{ body: { padding: 0 } }}
          >
            {menuNode}
          </Drawer>
        )}

        {/* ── Content ───────────────────────────────────────────── */}
        <Content style={{
          marginLeft: isMobile ? 0 : (collapsed ? 80 : 216),
          transition: 'margin-left 0.2s',
          padding: isMobile ? 16 : 24,
          minHeight: 'calc(100vh - 56px)',
          background: '#F2F3F5',
        }}>
          <div className="page-enter">
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}
