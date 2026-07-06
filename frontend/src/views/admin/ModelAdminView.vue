<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { adminApi } from '@/api/admin'

const rows = ref<any[]>([])
const monitor = ref<any>({})
const monitorLoading = ref(true)
const scenarios = ref<Array<{ id: string; name: string }>>([])
const visible = ref(false)
const drawerVisible = ref(false)
const drawerWidth = ref(Math.min(Math.max(Number(localStorage.getItem('admin-model-detail-drawer-width')) || 680, 480), 1200))
const drawerResizing = ref(false)
const detailLoading = ref(false)
const detail = ref<any>(null)
const detailChartEl = ref<HTMLDivElement | null>(null)
let detailChart: echarts.ECharts | null = null
let chartResizeObserver: ResizeObserver | null = null
const editingId = ref<number | null>(null)
const apiKeyInput = ref('')
const editingHasKey = ref(false)
const apiKeyIsPlaceholder = ref(false)
const API_KEY_MASK = '********'
const form = reactive<any>({
  model_type: 'llm',
  scenario: 'qa',
  is_primary: true,
  model_name: '',
  version: '',
  api_endpoint: '',
  config: {
    temperature: 0.2,
    max_tokens: 2048,
  },
  is_active: true,
})

const monitorSummary = computed(() => monitor.value?.summary || monitor.value || {})

const monitorCards = computed(() => {
  const m = monitorSummary.value || {}
  return [
    { key: 'calls', label: '今日总调用次数', value: m.total_calls ?? 0, sub: 'LLM 真实调用', accent: 'blue' },
    { key: 'tokens', label: 'Token 消耗总计', value: formatTokens(m.total_tokens), sub: '今日累计', accent: 'indigo' },
    { key: 'success', label: '平均成功率', value: `${m.success_rate ?? 100}%`, sub: `成功 ${m.success_count ?? 0} 次`, accent: 'emerald' },
    { key: 'p95', label: 'P95 延迟', value: m.p95_latency_ms ? `${m.p95_latency_ms} ms` : '—', sub: m.p95_label || '暂无数据', accent: 'cyan' },
  ]
})

const typeLabel: Record<string, string> = {
  llm: 'LLM',
  vector: '向量',
  reranker: '重排',
  parse: '解析',
}

function isLlmRow(row: any) {
  return row?.model_type === 'llm'
}

function configDetailItems(row: any) {
  const cfg = row?.config || {}
  if (row?.model_type === 'llm') {
    return [
      { label: '应用场景', value: row.scenario_name || row.scenario || '—' },
      { label: '路由角色', value: row.is_primary ? 'Primary 主干' : 'Fallback 备用' },
      { label: 'Temperature', value: cfg.temperature ?? '—' },
      { label: 'Max Tokens', value: cfg.max_tokens ?? '—' },
      { label: 'API Key', value: cfg.has_api_key ? '已配置' : '未配置' },
    ]
  }
  if (row?.model_type === 'vector') {
    return [
      { label: '向量维度', value: cfg.dim ?? '—' },
      { label: 'Normalize', value: cfg.normalize ? '是' : '否' },
    ]
  }
  if (row?.model_type === 'reranker') {
    return [{ label: 'Top N', value: cfg.top_n ?? '—' }]
  }
  if (row?.model_type === 'parse') {
    const chain = Array.isArray(cfg.engine_chain) ? cfg.engine_chain.join(' → ') : '—'
    return [{ label: '引擎链', value: chain }]
  }
  return []
}

function formatTokens(n: number | undefined) {
  const v = Number(n || 0)
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1000) return `${(v / 1000).toFixed(1)}K`
  return String(v)
}

async function loadMonitor() {
  monitorLoading.value = true
  try {
    monitor.value = await adminApi.modelsMonitor()
  } catch {
    monitor.value = {}
  } finally {
    monitorLoading.value = false
  }
}

async function loadScenarios() {
  try {
    scenarios.value = await adminApi.modelScenarios()
  } catch {
    scenarios.value = []
  }
}

async function loadConfig() {
  rows.value = await adminApi.models()
}

async function load() {
  await Promise.all([loadMonitor(), loadConfig(), loadScenarios()])
}

onMounted(() => {
  load()
  window.addEventListener('resize', onWindowResize)
})

function openCreate() {
  editingId.value = null
  apiKeyInput.value = ''
  editingHasKey.value = false
  apiKeyIsPlaceholder.value = false
  Object.assign(form, {
    model_type: 'llm',
    scenario: 'qa',
    is_primary: true,
    model_name: '',
    version: '',
    api_endpoint: '',
    config: { temperature: 0.2, max_tokens: 2048 },
    is_active: true,
  })
  visible.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  editingHasKey.value = !!row.config?.has_api_key
  if (editingHasKey.value) {
    apiKeyInput.value = API_KEY_MASK
    apiKeyIsPlaceholder.value = true
  } else {
    apiKeyInput.value = ''
    apiKeyIsPlaceholder.value = false
  }
  Object.assign(form, {
    model_type: row.model_type,
    scenario: row.scenario || 'qa',
    is_primary: !!row.is_primary,
    model_name: row.model_name,
    version: row.version,
    api_endpoint: row.api_endpoint,
    config: {
      temperature: row.config?.temperature ?? 0.2,
      max_tokens: row.config?.max_tokens ?? 2048,
    },
    is_active: row.is_active,
  })
  visible.value = true
}

function onApiKeyFocus() {
  if (apiKeyIsPlaceholder.value) {
    apiKeyInput.value = ''
    apiKeyIsPlaceholder.value = false
  }
}

function onApiKeyBlur() {
  if (editingId.value && editingHasKey.value && !apiKeyInput.value.trim()) {
    apiKeyInput.value = API_KEY_MASK
    apiKeyIsPlaceholder.value = true
  }
}

function buildPayload() {
  const payload: Record<string, any> = {
    model_type: form.model_type,
    model_name: form.model_name,
    version: form.version,
    api_endpoint: form.api_endpoint,
    is_active: form.is_active,
    config: { ...form.config },
  }
  if (form.model_type === 'llm') {
    payload.scenario = form.scenario
    payload.is_primary = !!form.is_primary
    const key = apiKeyInput.value.trim()
    if (key && !apiKeyIsPlaceholder.value && key !== API_KEY_MASK) {
      payload.config.api_key = key
    }
  }
  return payload
}

async function save() {
  if (!form.model_name?.trim()) {
    ElMessage.error('请填写模型名称')
    return
  }
  if (form.model_type === 'llm') {
    if (!form.scenario) {
      ElMessage.error('请选择应用场景')
      return
    }
    if (!form.api_endpoint?.trim()) {
      ElMessage.error('请填写调用地址')
      return
    }
  }
  const payload = buildPayload()
  if (editingId.value) {
    await adminApi.updateModel(editingId.value, payload)
    ElMessage.success('模型已更新')
  } else {
    if (form.model_type === 'llm' && form.is_active && !apiKeyInput.value.trim()) {
      ElMessage.error('新建并启用 LLM 必须填写 API Key')
      return
    }
    await adminApi.saveModel(payload)
    ElMessage.success('模型已添加')
  }
  visible.value = false
  await load()
}

async function handleToggle(row: any) {
  await adminApi.updateModel(row.id, { is_active: row.is_active })
  ElMessage.success('状态已更新')
  await loadConfig()
}

function getRowClassName({ row }: { row: any }) {
  return !row.is_active ? 'disabled-row' : ''
}

async function openDetail(row: any) {
  detailChart?.dispose()
  detailChart = null
  chartResizeObserver?.disconnect()
  drawerVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await adminApi.modelDetail(row.id)
    await nextTick()
    renderDetailChart()
  } catch {
    ElMessage.error('加载模型详情失败')
    drawerVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

function formatChartAxisTokens(n: number) {
  const v = Number(n || 0)
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1000) return `${(v / 1000).toFixed(1)}K`
  return String(v)
}

const detailHasTrend = computed(() => {
  const trend = detail.value?.last_7_days || []
  return trend.some((d: any) => (d.calls ?? 0) > 0 || (d.tokens ?? 0) > 0)
})

function observeDetailChart() {
  chartResizeObserver?.disconnect()
  if (!detailChartEl.value) return
  chartResizeObserver = new ResizeObserver(() => {
    detailChart?.resize()
  })
  chartResizeObserver.observe(detailChartEl.value)
}

function renderDetailChart() {
  if (!detailChartEl.value || !detail.value?.last_7_days?.length || !detailHasTrend.value) return
  if (!detailChart) detailChart = echarts.init(detailChartEl.value)
  const trend = detail.value.last_7_days
  detailChart.setOption(
    {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        confine: true,
        appendToBody: true,
        formatter(params: any) {
          const items = Array.isArray(params) ? params : [params]
          const date = items[0]?.axisValue || ''
          const lines = items.map((p: any) => {
            const val = p.seriesName === 'Token' ? formatTokens(p.value) : p.value
            return `${p.marker}${p.seriesName}: ${val}`
          })
          return [date, ...lines].join('<br/>')
        },
      },
      legend: {
        data: ['调用次数', 'Token'],
        bottom: 2,
        left: 'center',
        itemWidth: 12,
        itemHeight: 8,
        textStyle: { fontSize: 11, color: '#64748b' },
      },
      grid: { top: 24, right: 16, bottom: 40, left: 16, containLabel: true },
      xAxis: {
        type: 'category',
        boundaryGap: true,
        data: trend.map((d: any) => {
          const p = d.date.split('-')
          return `${p[1]}/${p[2]}`
        }),
        axisLabel: { fontSize: 11, color: '#64748b' },
        axisLine: { lineStyle: { color: '#e2e8f0' } },
      },
      yAxis: [
        {
          type: 'value',
          name: '次数',
          minInterval: 1,
          nameTextStyle: { fontSize: 11, color: '#64748b' },
          axisLabel: { fontSize: 11, color: '#64748b' },
          splitLine: { lineStyle: { type: 'dashed', color: '#f1f5f9' } },
        },
        {
          type: 'value',
          name: 'Token',
          nameTextStyle: { fontSize: 11, color: '#64748b' },
          axisLabel: { fontSize: 11, color: '#64748b', formatter: (v: number) => formatChartAxisTokens(v) },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: '调用次数',
          type: 'bar',
          data: trend.map((d: any) => d.calls),
          barMaxWidth: 28,
          itemStyle: { color: '#2563eb', borderRadius: [2, 2, 0, 0] },
        },
        {
          name: 'Token',
          type: 'line',
          yAxisIndex: 1,
          smooth: true,
          data: trend.map((d: any) => d.tokens),
          symbol: 'circle',
          symbolSize: 5,
          lineStyle: { width: 2, color: '#6366f1' },
          itemStyle: { color: '#6366f1' },
        },
      ],
    },
    true,
  )
  detailChart.resize()
  observeDetailChart()
}

function drawerWidthBounds() {
  return {
    min: 480,
    max: Math.min(Math.floor(window.innerWidth * 0.92), 1200),
  }
}

function clampDrawerWidth(width: number) {
  const { min, max } = drawerWidthBounds()
  return Math.max(min, Math.min(max, width))
}

function startDrawerResize(e: MouseEvent) {
  e.preventDefault()
  drawerResizing.value = true
  const startX = e.clientX
  const startWidth = drawerWidth.value
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'

  const onMove = (ev: MouseEvent) => {
    drawerWidth.value = clampDrawerWidth(startWidth + (startX - ev.clientX))
    detailChart?.resize()
  }
  const onUp = () => {
    drawerResizing.value = false
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    localStorage.setItem('admin-model-detail-drawer-width', String(drawerWidth.value))
    detailChart?.resize()
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function onDrawerOpened() {
  nextTick(() => {
    requestAnimationFrame(() => {
      renderDetailChart()
      detailChart?.resize()
    })
  })
}

function onWindowResize() {
  drawerWidth.value = clampDrawerWidth(drawerWidth.value)
  if (drawerVisible.value) detailChart?.resize()
}

onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize)
  chartResizeObserver?.disconnect()
  detailChart?.dispose()
  detailChart = null
})
</script>

<template>
  <div class="admin-page">
    <section v-if="monitorLoading" class="admin-metrics-bar">
      <div v-for="i in 4" :key="i" class="admin-metric">
        <div class="sk-line" /><div class="sk-line lg" />
      </div>
    </section>

    <section v-else class="admin-metrics-bar">
      <template v-for="(card, idx) in monitorCards" :key="card.key">
        <div v-if="idx > 0" class="admin-metric-divider" />
        <div class="admin-metric" :class="`admin-metric--${card.accent}`">
          <span class="admin-metric-label">{{ card.label }}</span>
          <span class="admin-metric-value is-accent">{{ card.value }}</span>
          <span class="admin-metric-sub">{{ card.sub }}<template v-if="idx === 0 && monitor.date"> · {{ monitor.date }}</template></span>
        </div>
      </template>
    </section>

    <div class="admin-toolbar">
      <div class="admin-toolbar-left">
        <span class="admin-toolbar-title">模型列表与配置</span>
        <span class="admin-toolbar-meta">按业务场景配置 LLM 主备路由</span>
      </div>
      <div class="admin-toolbar-right">
        <el-button text :loading="monitorLoading" @click="loadMonitor">刷新监控</el-button>
        <el-button text @click="loadConfig">刷新列表</el-button>
        <el-button type="primary" plain size="small" @click="openCreate">新增模型</el-button>
      </div>
    </div>

    <div class="admin-el-table">
      <el-table :data="rows" size="default" height="calc(100vh - 280px)" :row-class-name="getRowClassName">
        <el-table-column label="序号" width="64" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column prop="model_type" label="类型" width="88">
          <template #default="{ row }">
            <span class="type-text admin-tag is-type">{{ typeLabel[row.model_type] || row.model_type }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="model_name" label="模型名称" min-width="220">
          <template #default="{ row }">
            <div class="model-name-cell">
              <span class="model-name-text">{{ row.model_name }}</span>
              <div v-if="isLlmRow(row)" class="model-meta">
                <span v-if="row.scenario_name" class="admin-tag is-scenario">{{ row.scenario_name }}</span>
                <span class="admin-tag" :class="row.is_primary ? 'is-primary' : 'is-fallback'">
                  {{ row.is_primary ? '主路由' : '备用' }}
                </span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="88" />
        <el-table-column prop="api_endpoint" label="调用地址" min-width="140" show-overflow-tooltip />
        <el-table-column label="今日调用" width="88" align="right">
          <template #default="{ row }">{{ row.today_stats?.calls ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="Token" width="80" align="right">
          <template #default="{ row }">{{ formatTokens(row.today_stats?.tokens) }}</template>
        </el-table-column>
        <el-table-column label="成功率" width="80" align="right">
          <template #default="{ row }">
            {{ row.today_stats?.calls ? `${row.today_stats.success_rate}%` : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="API Key" width="80">
          <template #default="{ row }">
            <span v-if="row.model_type === 'llm'" class="key-text">
              {{ row.config?.has_api_key ? '已配置' : '—' }}
            </span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="启用" width="72">
          <template #default="{ row }">
            <el-switch v-model="row.is_active" size="small" @change="handleToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="visible" :title="editingId ? '编辑模型配置' : '新增模型配置'" width="580px">
      <el-form label-position="top" :model="form">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="模型类型">
              <el-select v-model="form.model_type" class="w-full">
                <el-option label="解析模型" value="parse" />
                <el-option label="向量模型" value="vector" />
                <el-option label="重排模型" value="reranker" />
                <el-option label="大语言模型" value="llm" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="版本">
              <el-input v-model="form.version" placeholder="如 v1.0" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="模型名称">
          <el-input v-model="form.model_name" />
        </el-form-item>
        <el-form-item label="调用地址">
          <el-input v-model="form.api_endpoint" placeholder="https://api.example.com/v1" />
        </el-form-item>
        <template v-if="form.model_type === 'llm'">
          <el-form-item label="应用场景" required>
            <el-select v-model="form.scenario" class="w-full" placeholder="选择业务场景">
              <el-option v-for="s in scenarios" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="路由角色" required>
            <el-radio-group v-model="form.is_primary" class="role-radio-group">
              <el-radio :label="true">作为主干模型 (Primary)</el-radio>
              <el-radio :label="false">作为降级备用 (Fallback)</el-radio>
            </el-radio-group>
            <p v-if="form.is_primary" class="form-hint">保存后将自动替换该场景下现有的主模型</p>
          </el-form-item>
          <el-form-item label="API Key">
            <el-input
              v-model="apiKeyInput"
              :type="apiKeyIsPlaceholder ? 'text' : 'password'"
              :show-password="!apiKeyIsPlaceholder"
              autocomplete="new-password"
              class="api-key-input"
              :class="{ 'is-masked': apiKeyIsPlaceholder }"
              :placeholder="editingId && !editingHasKey ? '留空则不修改' : '请输入 API Key'"
              @focus="onApiKeyFocus"
              @blur="onApiKeyBlur"
            />
          </el-form-item>
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="Temperature">
                <el-input-number v-model="form.config.temperature" :min="0" :max="2" :step="0.1" class="w-full" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="Max Tokens">
                <el-input-number v-model="form.config.max_tokens" :min="256" :max="128000" :step="256" class="w-full" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>
        <el-form-item label="是否启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="drawerVisible"
      :title="detail ? `${typeLabel[detail.model_type] || detail.model_type} · ${detail.model_name}` : '模型详情'"
      :size="`${drawerWidth}px`"
      :class="['model-detail-drawer', { 'is-resizing': drawerResizing }]"
      destroy-on-close
      @opened="onDrawerOpened"
      @closed="detail = null"
    >
      <div class="drawer-resize-handle" title="拖拽调整宽度" @mousedown="startDrawerResize" />
      <div v-loading="detailLoading" class="detail-drawer">
        <template v-if="detail">
          <section class="detail-block">
            <h3 class="detail-heading">基础信息</h3>
            <dl class="detail-dl">
              <div><dt>类型</dt><dd>{{ typeLabel[detail.model_type] || detail.model_type }}</dd></div>
              <div v-if="detail.model_type === 'llm'"><dt>应用场景</dt><dd>{{ detail.scenario_name || detail.scenario || '—' }}</dd></div>
              <div v-if="detail.model_type === 'llm'"><dt>路由角色</dt><dd>{{ detail.is_primary ? '主路由' : '备用路由' }}</dd></div>
              <div><dt>版本</dt><dd>{{ detail.version || '—' }}</dd></div>
              <div><dt>调用地址</dt><dd class="mono">{{ detail.api_endpoint || '—' }}</dd></div>
              <div><dt>状态</dt><dd>{{ detail.is_active ? '已启用' : '未启用' }}</dd></div>
              <div><dt>更新时间</dt><dd>{{ detail.updated_at?.replace('T', ' ').slice(0, 19) || '—' }}</dd></div>
            </dl>
          </section>

          <section class="detail-block">
            <h3 class="detail-heading">配置参数</h3>
            <dl class="detail-dl">
              <div v-for="item in configDetailItems(detail)" :key="item.label">
                <dt>{{ item.label }}</dt><dd>{{ item.value }}</dd>
              </div>
            </dl>
          </section>

          <section class="detail-block">
            <h3 class="detail-heading">运行统计</h3>
            <div class="detail-metrics">
              <div class="detail-metric">
                <span class="admin-metric-label">今日调用</span>
                <span class="detail-metric-value">{{ detail.today?.calls ?? 0 }}</span>
              </div>
              <div class="detail-metric">
                <span class="admin-metric-label">今日 Token</span>
                <span class="detail-metric-value">{{ formatTokens(detail.today?.tokens) }}</span>
              </div>
              <div class="detail-metric">
                <span class="admin-metric-label">成功率</span>
                <span class="detail-metric-value">{{ detail.today?.success_rate ?? 100 }}%</span>
              </div>
              <div class="detail-metric">
                <span class="admin-metric-label">平均延迟</span>
                <span class="detail-metric-value">{{ detail.today?.avg_latency_ms ? `${detail.today.avg_latency_ms} ms` : '—' }}</span>
              </div>
            </div>
            <p class="detail-period">
              近 7 日：{{ detail.period_7d?.total_calls ?? 0 }} 次 · {{ formatTokens(detail.period_7d?.total_tokens) }} Token · 成功率 {{ detail.period_7d?.success_rate ?? 100 }}%
            </p>
            <div class="detail-chart-wrap">
              <div v-if="!detailHasTrend" class="detail-chart-empty">近 7 日暂无调用趋势数据</div>
              <div v-show="detailHasTrend" ref="detailChartEl" class="detail-chart" />
            </div>
          </section>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.model-name-cell {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.125rem 0;
}

.model-name-text {
  font-weight: 600;
  color: var(--academic-text-main, #0f172a);
}

.model-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.muted,
.key-text {
  font-size: 0.75rem;
  color: #94a3b8;
}

.form-hint {
  margin: 0.5rem 0 0;
  font-size: 0.6875rem;
  color: #d97706;
}

.role-radio-group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
}

.detail-drawer {
  padding: 0 0.25rem 1rem;
  min-height: 200px;
}

.model-detail-drawer :deep(.el-drawer__body) {
  position: relative;
  overflow: auto;
}

.model-detail-drawer.is-resizing :deep(.el-drawer) {
  transition: none !important;
}

.drawer-resize-handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 8px;
  margin-left: -4px;
  cursor: col-resize;
  z-index: 20;
}

.drawer-resize-handle::after {
  content: '';
  position: absolute;
  left: 3px;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 48px;
  background: #e2e8f0;
}

.drawer-resize-handle:hover::after,
.model-detail-drawer.is-resizing .drawer-resize-handle::after {
  background: var(--admin-accent, #2563eb);
}

.detail-block {
  margin-bottom: 1.5rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid #f1f5f9;
}

.detail-block:last-child {
  border-bottom: none;
}

.detail-heading {
  margin: 0 0 0.75rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #0f172a;
}

.detail-dl {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.detail-dl div {
  display: grid;
  grid-template-columns: 6rem 1fr;
  gap: 0.75rem;
  font-size: 0.8125rem;
}

.detail-dl dt {
  color: #64748b;
  font-weight: 500;
}

.detail-dl dd {
  margin: 0;
  color: #334155;
  word-break: break-all;
}

.detail-dl .mono {
  font-family: ui-monospace, monospace;
  font-size: 0.75rem;
}

.detail-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem 1.5rem;
  margin-bottom: 0.75rem;
}

.detail-metric {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.detail-metric-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--admin-accent, #2563eb);
  letter-spacing: -0.02em;
}

.detail-period {
  margin: 0 0 0.75rem;
  font-size: 0.75rem;
  color: #64748b;
}

.detail-chart-wrap {
  padding-top: 0.5rem;
}

.detail-chart {
  width: 100%;
  height: 260px;
}

.detail-chart-empty {
  height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8125rem;
  color: #94a3b8;
}

.api-key-input.is-masked :deep(.el-input__inner) {
  letter-spacing: 0.12em;
  color: #64748b;
}

.w-full {
  width: 100%;
}

.disabled-row {
  opacity: 0.45;
}

.sk-line {
  height: 10px;
  background: #e2e8f0;
  margin-bottom: 0.5rem;
  width: 50%;
}

.sk-line.lg {
  height: 22px;
  width: 35%;
}

.admin-metrics-bar:has(.sk-line) {
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}
</style>
