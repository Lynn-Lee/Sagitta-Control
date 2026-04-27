import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Spin } from 'antd'
import AuthGuard from '@/components/common/AuthGuard'
import PermissionGuard from '@/components/common/PermissionGuard'
import { useAuthStore } from '@/store/auth'
import { getPostLoginPath } from '@/utils/postLogin'

const LoginPage            = lazy(() => import('@/pages/auth/LoginPage'))
const OAuthCallbackPage    = lazy(() => import('@/pages/auth/OAuthCallbackPage'))
const ProfilePage          = lazy(() => import('@/pages/auth/ProfilePage'))
const MainLayout           = lazy(() => import('@/components/layout/MainLayout'))
const DashboardQuery       = lazy(() => import('@/pages/dashboard/DashboardPage').then(m => ({ default: m.QueryDashboardPage })))
const DashboardWorkflow    = lazy(() => import('@/pages/dashboard/DashboardPage').then(m => ({ default: m.WorkflowDashboardPage })))
const DashboardArchive     = lazy(() => import('@/pages/dashboard/DashboardPage').then(m => ({ default: m.ArchiveDashboardPage })))
const DashboardInstance    = lazy(() => import('@/pages/dashboard/DashboardPage').then(m => ({ default: m.InstanceDashboardPage })))
const WorkflowList         = lazy(() => import('@/pages/workflow/WorkflowList'))
const WorkflowSubmit       = lazy(() => import('@/pages/workflow/WorkflowSubmit'))
const WorkflowDetail       = lazy(() => import('@/pages/workflow/WorkflowDetail'))
const WorkflowTemplatePage = lazy(() => import('@/pages/workflow/WorkflowTemplatePage'))
const QueryPage            = lazy(() => import('@/pages/query/QueryPage'))
const QueryPrivPage        = lazy(() => import('@/pages/query/QueryPrivPage'))
const QueryHistoryPage     = lazy(() => import('@/pages/query/QueryHistoryPage'))
const MonitorPage          = lazy(() => import('@/pages/monitor/MonitorPage'))
const DiagnosticPage       = lazy(() => import('@/pages/diagnostic/DiagnosticPage'))
const SqlAnalysisPage      = lazy(() => import('@/pages/slowlog/SlowlogPage'))
const DataDictPage         = lazy(() => import('@/pages/schema/DataDictPage'))
const InstanceList         = lazy(() => import('@/pages/instance/InstanceList'))
const UserManagement       = lazy(() => import('@/pages/system/UserManagement'))
const ResourceGroupManagement = lazy(() => import('@/pages/system/ResourceGroupManagement'))
const SystemConfig         = lazy(() => import('@/pages/system/SystemConfig'))
const MaskingRulePage      = lazy(() => import('@/pages/masking/MaskingRulePage'))
const ApprovalFlowPage     = lazy(() => import('@/pages/system/ApprovalFlowPage'))
const RoleManagement       = lazy(() => import('@/pages/system/RoleManagement'))
const UserGroupManagement  = lazy(() => import('@/pages/system/UserGroupManagement'))
const AuditLog             = lazy(() => import('@/pages/audit/AuditLog'))
const Placeholder          = lazy(() => import('@/pages/Placeholder'))
const ArchivePage          = lazy(() => import('@/pages/archive/ArchivePage'))

const Loading = () => (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
    <Spin size="large" />
  </div>
)

function DefaultAuthedRoute() {
  const user = useAuthStore((s) => s.user)
  return <Navigate to={getPostLoginPath(user?.permissions || [])} replace />
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/oauth/callback" element={<OAuthCallbackPage />} />
        <Route path="/" element={<AuthGuard><MainLayout /></AuthGuard>}>
          <Route index element={<DefaultAuthedRoute />} />
          <Route path="dashboard"            element={<PermissionGuard permission="menu_dashboard"><Navigate to="/dashboard/query" replace /></PermissionGuard>} />
          <Route path="dashboard/query"      element={<PermissionGuard permission="menu_dashboard"><DashboardQuery /></PermissionGuard>} />
          <Route path="dashboard/workflow"   element={<PermissionGuard permission="menu_dashboard"><DashboardWorkflow /></PermissionGuard>} />
          <Route path="dashboard/archive"    element={<PermissionGuard permission="menu_dashboard"><DashboardArchive /></PermissionGuard>} />
          <Route path="dashboard/instance"   element={<PermissionGuard permission="menu_dashboard"><DashboardInstance /></PermissionGuard>} />
          <Route path="workflow"             element={<PermissionGuard permission="menu_sqlworkflow"><WorkflowList /></PermissionGuard>} />
          <Route path="workflow/submit"      element={<PermissionGuard permission="menu_sqlworkflow"><WorkflowSubmit /></PermissionGuard>} />
          <Route path="workflow/templates"   element={<PermissionGuard permission="menu_sqlworkflow"><WorkflowTemplatePage /></PermissionGuard>} />
          <Route path="workflow/:id"         element={<PermissionGuard permission="menu_sqlworkflow"><WorkflowDetail /></PermissionGuard>} />
          <Route path="query"                element={<PermissionGuard permission="menu_query"><QueryPage /></PermissionGuard>} />
          <Route path="query/privileges"     element={<PermissionGuard permission="menu_query"><QueryPrivPage /></PermissionGuard>} />
          <Route path="query/history"        element={<PermissionGuard permission="menu_query"><QueryHistoryPage /></PermissionGuard>} />
          <Route path="monitor"              element={<PermissionGuard permission="menu_monitor"><MonitorPage /></PermissionGuard>} />
          <Route path="sql-analysis"         element={<PermissionGuard permission="menu_ops"><SqlAnalysisPage /></PermissionGuard>} />
          <Route path="slowlog"              element={<Navigate to="/sql-analysis" replace />} />
          <Route path="diagnostic"           element={<PermissionGuard permission="menu_ops"><DiagnosticPage /></PermissionGuard>} />
          <Route path="archive"              element={<PermissionGuard anyPermissions={['archive_apply', 'archive_review', 'archive_execute']}><ArchivePage /></PermissionGuard>} />
          <Route path="optimize"             element={<Navigate to="/sql-analysis" replace />} />
          <Route path="schema"               element={<PermissionGuard permission="menu_schema"><DataDictPage /></PermissionGuard>} />
          <Route path="instance"             element={<PermissionGuard permission="instance_manage"><InstanceList /></PermissionGuard>} />
          <Route path="system/users"         element={<PermissionGuard permission="menu_system"><UserManagement /></PermissionGuard>} />
          <Route path="system/groups"        element={<PermissionGuard permission="menu_system"><ResourceGroupManagement /></PermissionGuard>} />
          <Route path="system/roles"         element={<PermissionGuard permission="menu_system"><RoleManagement /></PermissionGuard>} />
          <Route path="system/user-groups"   element={<PermissionGuard permission="menu_system"><UserGroupManagement /></PermissionGuard>} />
          <Route path="system/approval-flows" element={<PermissionGuard permission="menu_system"><ApprovalFlowPage /></PermissionGuard>} />
          <Route path="system/config"        element={<PermissionGuard permission="menu_system"><SystemConfig /></PermissionGuard>} />
          <Route path="masking"              element={<PermissionGuard permission="menu_system"><MaskingRulePage /></PermissionGuard>} />
          <Route path="audit"                element={<PermissionGuard permission="menu_audit"><AuditLog /></PermissionGuard>} />
          <Route path="profile"              element={<ProfilePage />} />
          <Route path="*"                    element={<DefaultAuthedRoute />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
