import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import App from './App'
import { appLocale, zhCNValidateMessages } from '@/utils/locale'
import '@/styles/globals.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
})

// ── SagittaDB Design Token ────────────────────────────────────
const antTheme = {
  token: {
    // 字体：Inter + Noto Sans SC 配合系统字体
    fontFamily: `'Inter', 'Noto Sans SC', -apple-system, BlinkMacSystemFont,
                 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif`,
    fontSize:         14,
    fontSizeLG:       15,
    fontSizeXL:       18,
    fontSizeHeading1: 28,
    fontSizeHeading2: 22,
    fontSizeHeading3: 18,
    fontSizeHeading4: 16,

    // 品牌主色 — Space Tech Blue
    colorPrimary:   '#165DFF',
    colorLink:      '#165DFF',
    colorSuccess:   '#00B42A',
    colorWarning:   '#FF7D00',
    colorError:     '#F53F3F',
    colorInfo:      '#165DFF',

    // 背景
    colorBgLayout:    '#F2F3F5',
    colorBgContainer: '#FFFFFF',
    colorBgElevated:  '#FFFFFF',

    // 文字
    colorText:            '#1D2129',
    colorTextSecondary:   '#4E5969',
    colorTextDisabled:    '#C9CDD4',
    colorTextHeading:     '#1D2129',
    colorTextDescription: '#86909C',

    // 边框
    colorBorder:          '#E5E6EB',
    colorBorderSecondary: '#F0F1F5',

    // 圆角
    borderRadius:   6,
    borderRadiusLG: 8,
    borderRadiusSM: 4,
    borderRadiusXS: 3,

    // 无阴影
    boxShadow:          'none',
    boxShadowSecondary: 'none',
    boxShadowTertiary:  'none',

    // 间距
    padding:   16,
    paddingLG: 24,
    paddingSM: 12,
    paddingXS: 8,
    margin:    16,
    marginLG:  24,
    marginSM:  12,

    // 动效
    motionDurationFast: '0.1s',
    motionDurationMid:  '0.2s',
    motionDurationSlow: '0.25s',

    // 按钮：所有尺寸入口统一为 36px，避免页面操作区高低不齐
    controlHeight:   36,
    controlHeightSM: 36,
    controlHeightLG: 36,
  },
  components: {
    Layout: {
      headerBg:      '#0F172A',   // 技术炭黑
      headerColor:   '#FFFFFF',
      headerHeight:  56,
      siderBg:       '#FFFFFF',
      bodyBg:        '#F2F3F5',
      triggerBg:     '#F2F3F5',
      triggerColor:  '#4E5969',
    },
    Menu: {
      itemSelectedBg:    '#EEF3FF',
      itemSelectedColor: '#165DFF',
      itemHoverBg:       '#F2F3F5',
      itemActiveBg:      '#EEF3FF',
      subMenuItemBg:     '#FAFAFA',
      fontSize:          13,
    },
    Table: {
      borderColor:        '#E5E6EB',
      headerBg:           '#F7F8FA',
      headerColor:        '#4E5969',
      rowHoverBg:         '#EEF3FF',
      cellPaddingBlock:   10,
      cellPaddingInline:  14,
      fontSize:           13,
    },
    Button: {
      boxShadow:     'none',
      primaryShadow: 'none',
      defaultShadow: 'none',
      dangerShadow:  'none',
      borderRadius:  6,
      fontWeight:    500,
      paddingInline:   14,
      paddingInlineSM: 14,
      paddingInlineLG: 14,
    },
    Card: {
      boxShadow:    'none',
      borderRadius: 8,
      paddingLG:    20,
    },
    Tabs: {
      itemSelectedColor: '#165DFF',
      inkBarColor:       '#165DFF',
      itemHoverColor:    '#4080FF',
    },
    Form: {
      labelColor:    '#1D2129',
      labelFontSize: 13,
      itemMarginBottom: 16,
    },
    Input: {
      activeBorderColor: '#165DFF',
      hoverBorderColor:  '#4080FF',
      activeShadow:      '0 0 0 3px rgba(22,93,255,0.12)',
      borderRadius:      6,
    },
    Select: {
      activeBorderColor: '#165DFF',
      hoverBorderColor:  '#4080FF',
      activeShadow:      '0 0 0 3px rgba(22,93,255,0.12)',
    },
    Modal: {
      borderRadiusLG: 12,
    },
    Drawer: {
      borderRadiusLG: 12,
    },
    Tag: {
      borderRadiusSM: 4,
    },
    Badge: {
      colorPrimary: '#165DFF',
    },
    Steps: {
      colorPrimary: '#165DFF',
    },
    Alert: {
      borderRadiusLG: 8,
    },
    Tooltip: {
      borderRadius: 6,
    },
    Progress: {
      colorInfo: '#165DFF',
    },
    Switch: {
      colorPrimary: '#165DFF',
    },
    Checkbox: {
      colorPrimary: '#165DFF',
    },
    Radio: {
      colorPrimary: '#165DFF',
    },
  },
}

ConfigProvider.config({
  holderRender: (children) => (
    <ConfigProvider theme={antTheme} locale={appLocale} form={{ validateMessages: zhCNValidateMessages }}>
      {children}
    </ConfigProvider>
  ),
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfigProvider theme={antTheme} locale={appLocale} form={{ validateMessages: zhCNValidateMessages }}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ConfigProvider>
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  </React.StrictMode>,
)
