export function getPostLoginPath(permissions: string[] = []) {
  if (permissions.includes('menu_dashboard')) return '/dashboard'
  if (permissions.includes('menu_query')) return '/query'
  if (permissions.includes('menu_sqlworkflow')) return '/workflow'
  if (permissions.includes('menu_monitor')) return '/monitor'
  if (permissions.includes('menu_ops')) return '/slowlog'
  if (permissions.includes('instance_manage')) return '/instance'
  if (permissions.includes('menu_system')) return '/system/users'
  if (permissions.includes('menu_audit')) return '/audit'
  return '/profile'
}
