export const FAMILY = {
  universal: { label: '通用基础模型', cls: 'tag-family-universal' },
  deep: { label: '深度学习模型', cls: 'tag-family-deep' },
  lightweight: { label: '轻量模型', cls: 'tag-family-lightweight' },
  external: { label: '外部接入模型', cls: 'tag-family-external' }
}

export const TASK = { regression: '回归', classification: '分类' }

export const STATUS = {
  ready: { label: '未发布', type: 'info' },
  published: { label: '已发布', type: 'success' },
  archived: { label: '已下线', type: 'warning' }
}

export const JOB_STATUS = {
  queued: { label: '排队中', type: 'info' },
  running: { label: '运行中', type: 'primary' },
  succeeded: { label: '成功', type: 'success' },
  failed: { label: '失败', type: 'danger' },
  cancelled: { label: '已取消', type: 'warning' }
}

export const VISIBILITY = { private: '仅自己', team: '团队共享', public: '全平台公开' }

export const METRIC_LABELS = {
  r2: 'R²',
  mae: 'MAE',
  rmse: 'RMSE',
  accuracy: '准确率',
  f1_macro: 'F1（宏）',
  precision_macro: '精确率（宏）',
  recall_macro: '召回率（宏）',
  auc: 'AUC'
}

export const COLUMN_TYPES = {
  numeric: '数值',
  categorical: '类别',
  datetime: '日期',
  smiles: 'SMILES 分子',
  id: 'ID/编号',
  constant: '常量',
  text: '文本',
  empty: '空列'
}

export function fmt(v, digits = 4) {
  if (v === null || v === undefined || v === '') return '-'
  if (typeof v === 'number') {
    if (!isFinite(v)) return '-'
    if (Number.isInteger(v)) return String(v)
    const abs = Math.abs(v)
    if (abs !== 0 && (abs < 1e-3 || abs >= 1e6)) return v.toExponential(2)
    return Number(v.toFixed(digits)).toString()
  }
  return String(v)
}

export function metricEntries(metrics) {
  if (!metrics) return []
  return Object.keys(METRIC_LABELS)
    .filter((k) => metrics[k] !== undefined && metrics[k] !== null)
    .map((k) => ({ key: k, label: METRIC_LABELS[k], value: metrics[k], primary: metrics.primary === k }))
}

export function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}
