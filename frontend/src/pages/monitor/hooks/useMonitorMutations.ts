import { useMutation, type QueryClient } from '@tanstack/react-query'

import apiClient from '@/api/client'

import type { BulkCollectConfigResponse, MonitorInstance } from '../types'

type MonitorMutationParams = {
  activeId: number | null
  alertRulesText: string
  instances: MonitorInstance[]
  queryClient: QueryClient
  msgApi: any
  closeConfig: () => void
}

export function useMonitorMutations({
  activeId,
  alertRulesText,
  instances,
  queryClient,
  msgApi,
  closeConfig,
}: MonitorMutationParams) {
  const invalidateCollectConfigQueries = (instanceId?: number | null) => {
    queryClient.invalidateQueries({ queryKey: ['unified-collect-configs'] })
    queryClient.invalidateQueries({ queryKey: ['native-monitor-instances'] })
    queryClient.invalidateQueries({ queryKey: ['native-monitor-overview'] })
    queryClient.invalidateQueries({ queryKey: ['session-collect-configs'] })
    queryClient.invalidateQueries({ queryKey: ['slowlog-configs'] })
    if (instanceId) {
      queryClient.invalidateQueries({ queryKey: ['native-monitor-detail', instanceId] })
    } else {
      queryClient.invalidateQueries({ queryKey: ['native-monitor-detail'] })
    }
  }

  const saveConfig = useMutation({
    mutationFn: ({ instanceId, values }: { instanceId: number; values: any }) => apiClient.put(`/monitor/native/instances/${instanceId}/collect-configs/`, values).then(r => r.data),
    onSuccess: (_data, variables) => {
      invalidateCollectConfigQueries(variables.instanceId)
      closeConfig()
      msgApi.success('采集配置已保存')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '保存失败'),
  })
  const saveAllConfig = useMutation<BulkCollectConfigResponse, any, any>({
    mutationFn: (values: any) => apiClient.put<BulkCollectConfigResponse>('/monitor/native/collect-configs/bulk/', values).then(r => r.data),
    onSuccess: (result) => {
      invalidateCollectConfigQueries()
      closeConfig()
      msgApi.success(`已配置 ${result.success}/${result.total} 个实例${result.failed?.length ? `，失败 ${result.failed.length} 个` : ''}`)
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '批量保存失败'),
  })
  const disableAllConfig = useMutation<BulkCollectConfigResponse, any, void>({
    mutationFn: () => apiClient.put<BulkCollectConfigResponse>('/monitor/native/collect-configs/bulk/', {
      native: {
        is_enabled: false,
        collect_interval: 60,
        capacity_collect_interval: 3600,
        retention_days: 30,
      },
      session: {
        is_enabled: false,
        collect_interval: 60,
        retention_days: 30,
      },
      sql: {
        is_enabled: false,
        threshold_ms: 1000,
        collect_interval: 300,
        retention_days: 30,
        collect_limit: 100,
      },
    }).then(r => r.data),
    onSuccess: (result) => {
      invalidateCollectConfigQueries()
      msgApi.success(`已关闭 ${result.success}/${result.total} 个实例采集${result.failed?.length ? `，失败 ${result.failed.length} 个` : ''}`)
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '批量关闭失败'),
  })
  const collectNow = useMutation({
    mutationFn: (instanceId: number) => apiClient.post(`/monitor/native/instances/${instanceId}/collect/`).then(r => r.data),
    onSuccess: (_data, instanceId) => {
      queryClient.invalidateQueries({ queryKey: ['native-monitor-instances'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-overview'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-detail', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-trend', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-db-capacity', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-table-capacity'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-health', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-top-sql', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-waits', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-capacity-growth', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-engine-detail', instanceId] })
      queryClient.invalidateQueries({ queryKey: ['unified-collect-configs'] })
      msgApi.success('采集完成')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '采集失败'),
  })
  const collectAll = useMutation({
    mutationFn: async () => {
      let success = 0
      const failed: string[] = []
      for (const item of instances) {
        try {
          await apiClient.post(`/monitor/native/instances/${item.instance_id}/collect/`)
          success += 1
        } catch (error: any) {
          failed.push(`${item.instance_name}：${error.response?.data?.msg || '采集失败'}`)
        }
      }
      return { total: instances.length, success, failed }
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['native-monitor-instances'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-overview'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-detail'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-trend'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-db-capacity'] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-table-capacity'] })
      if (result.failed.length) {
        msgApi.warning(`已采集 ${result.success}/${result.total} 个实例，${result.failed.length} 个失败`)
      } else {
        msgApi.success(`已采集全部 ${result.total} 个实例`)
      }
    },
  })
  const saveAlertRules = useMutation({
    mutationFn: async () => {
      const payload = JSON.parse(alertRulesText || '{}')
      return apiClient.put(`/monitor/native/instances/${activeId}/alerts/`, payload).then(r => r.data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['native-monitor-alerts', activeId] })
      msgApi.success('告警规则已保存')
    },
    onError: (e: any) => msgApi.error(e instanceof SyntaxError ? '告警规则 JSON 格式不正确' : e.response?.data?.msg || '保存告警规则失败'),
  })
  const changeAlertEvent = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'ack' | 'silence' | 'resolve' | 'close' }) => {
      if (action === 'ack') return apiClient.post(`/monitor/alerts/events/${id}/ack`).then(r => r.data)
      if (action === 'silence') return apiClient.post(`/monitor/alerts/events/${id}/silence`, { minutes: 60 }).then(r => r.data)
      if (action === 'resolve') return apiClient.post(`/monitor/alerts/events/${id}/resolve`).then(r => r.data)
      return apiClient.post(`/monitor/alerts/events/${id}/close`, { reason: '监控页面关闭' }).then(r => r.data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['monitor-alert-events', activeId] })
      queryClient.invalidateQueries({ queryKey: ['native-monitor-alerts', activeId] })
      msgApi.success('告警状态已更新')
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '告警状态更新失败'),
  })

  return {
    saveConfig,
    saveAllConfig,
    disableAllConfig,
    collectNow,
    collectAll,
    saveAlertRules,
    changeAlertEvent,
    invalidateCollectConfigQueries,
  }
}
