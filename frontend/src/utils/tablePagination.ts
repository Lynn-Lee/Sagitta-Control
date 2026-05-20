import type { TablePaginationConfig } from 'antd/es/table'

export const TABLE_PAGE_SIZE_OPTIONS = ['10', '20', '50', '100', '200']

export const tablePaginationConfig: TablePaginationConfig = {
  showSizeChanger: true,
  pageSizeOptions: TABLE_PAGE_SIZE_OPTIONS,
}

export const getTablePaginationConfig = (
  config: TablePaginationConfig,
): TablePaginationConfig => ({
  ...tablePaginationConfig,
  ...config,
})
