// 工单模板文本归一化：把用户/后端传入的字面转义序列（\r\n、\n、\t）还原为真实换行/制表符。
// 收敛自 WorkflowSubmit 与 WorkflowTemplatePage 此前各自内联的同名实现。
export const normalizeTemplateText = (value?: string | null) =>
  (value || '')
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')
