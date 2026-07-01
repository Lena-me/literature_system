<script setup lang="ts">
import { onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { adminApi } from '@/api/admin'

const health = ref<any>({})
const ops = ref<any>({})
const daily = ref<any>({})
const chartEl = ref<HTMLDivElement | null>(null)
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const [h, o, d] = await Promise.all([
      adminApi.systemHealth(),
      adminApi.operationStats().catch(() => ({})),
      adminApi.dailyStats().catch(() => ({ dates: [], upload: [], parse: [], qa: [], report: [] }))
    ])
    health.value = h
    ops.value = o
    daily.value = d
    setTimeout(renderChart, 50)
  } finally {
    loading.value = false
  }
}

onMounted(load)

function renderChart() {
  if (!chartEl.value) return

  const chartInstance = echarts.init(chartEl.value)
  const dates = daily.value.dates || []
  const formattedDates = dates.map((d: string) => {
    const parts = d.split('-')
    return `${parts[1]}/${parts[2]}`
  })

  chartInstance.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: 'var(--academic-border)',
      borderWidth: 1,
      textStyle: {
        color: 'var(--academic-text-body)'
      },
      padding: [12, 16],
      borderRadius: 12,
      axisPointer: {
        type: 'cross',
        lineStyle: {
          color: 'var(--academic-border)',
          type: 'dashed'
        }
      }
    },
    legend: {
      data: ['上传', '解析', '问答', '报告'],
      top: 0,
      right: 0,
      textStyle: {
        color: 'var(--academic-text-muted)',
        fontSize: 12
      },
      itemWidth: 16,
      itemHeight: 8,
      itemGap: 20
    },
    grid: {
      top: 48,
      right: 20,
      bottom: 48,
      left: 56
    },
    xAxis: {
      type: 'category',
      data: formattedDates,
      axisLine: {
        lineStyle: {
          color: 'var(--academic-border)'
        }
      },
      axisLabel: {
        color: 'var(--academic-text-muted)',
        fontSize: 12
      },
      axisTick: {
        show: false
      }
    },
    yAxis: {
      type: 'value',
      axisLine: {
        show: false
      },
      axisLabel: {
        color: 'var(--academic-text-muted)',
        fontSize: 12
      },
      axisTick: {
        show: false
      },
      splitLine: {
        lineStyle: {
          color: 'var(--academic-border)',
          type: 'dashed'
        }
      }
    },
    series: [
      {
        name: '上传',
        type: 'line',
        smooth: true,
        data: daily.value.upload || [],
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: {
          color: '#2563EB'
        },
        lineStyle: {
          width: 3,
          color: '#2563EB'
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(37, 99, 235, 0.15)' },
              { offset: 1, color: 'rgba(37, 99, 235, 0.02)' }
            ]
          }
        }
      },
      {
        name: '解析',
        type: 'line',
        smooth: true,
        data: daily.value.parse || [],
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: {
          color: '#10B981'
        },
        lineStyle: {
          width: 3,
          color: '#10B981'
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(16, 185, 129, 0.15)' },
              { offset: 1, color: 'rgba(16, 185, 129, 0.02)' }
            ]
          }
        }
      },
      {
        name: '问答',
        type: 'line',
        smooth: true,
        data: daily.value.qa || [],
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: {
          color: '#8B5CF6'
        },
        lineStyle: {
          width: 3,
          color: '#8B5CF6'
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(139, 92, 246, 0.15)' },
              { offset: 1, color: 'rgba(139, 92, 246, 0.02)' }
            ]
          }
        }
      },
      {
        name: '报告',
        type: 'line',
        smooth: true,
        data: daily.value.report || [],
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: {
          color: '#F59E0B'
        },
        lineStyle: {
          width: 3,
          color: '#F59E0B'
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(245, 158, 11, 0.15)' },
              { offset: 1, color: 'rgba(245, 158, 11, 0.02)' }
            ]
          }
        }
      }
    ]
  })

  window.addEventListener('resize', () => {
    chartInstance.resize()
  })
}
</script>

<template>
  <div class="admin-dashboard" v-loading="loading" element-loading-text="加载中...">
    <div class="page-header">
      <div>
        <h1 class="page-title">系统运维总览</h1>
        <p class="page-subtitle">实时监控系统状态与业务数据</p>
      </div>
      <el-button class="btn-secondary" @click="load">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M4 20v-6h6"/><path d="M20.49 15a9 9 0 00-2.12-9.36L5 18"/></svg>
        <span>刷新</span>
      </el-button>
    </div>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon status-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-label">服务状态</div>
          <div class="stat-value" :class="{ healthy: health.status === 'ok' }">
            {{ health.status === 'ok' ? '运行正常' : '异常' }}
          </div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon redis-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-label">Redis数据库</div>
          <div class="stat-value" :class="{ healthy: health.redis === true }">
            {{ health.redis === true ? '运行正常' : (health.redis === false ? '连接失败' : '-') }}
          </div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon db-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <polyline points="12 22 12 15" />
            <polyline points="8 22 8 15" />
            <polyline points="16 22 16 15" />
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-label">向量库规模</div>
          <div class="stat-value">{{ ops.vector_db_total || 0 }}</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon user-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-label">用户总数</div>
          <div class="stat-value">{{ ops.total_users || 0 }}</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon active-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2v20" />
            <path d="m17 5-5 5-5-5" />
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-label">活跃用户</div>
          <div class="stat-value">{{ ops.active_users || 0 }}</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon upload-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-label">文献上传</div>
          <div class="stat-value">{{ ops.total_uploaded || 0 }}</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon parse-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
            <polyline points="10 9 9 9 8 9" />
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-label">成功解析</div>
          <div class="stat-value">{{ ops.total_parsed || 0 }}</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon qa-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-label">问答调用</div>
          <div class="stat-value">{{ ops.total_qa_calls || 0 }}</div>
        </div>
      </div>
    </div>

    <div class="chart-section soft-card">
      <div class="section-header">
        <h3 class="section-title">核心业务趋势</h3>
      </div>
      <div ref="chartEl" class="chart-container" />
    </div>
  </div>
</template>

<style scoped>
.admin-dashboard {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.page-header {
  margin-bottom: 8px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.btn-secondary {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 7px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  background: var(--academic-panel);
  border-color: var(--academic-border);
  color: var(--academic-text-body);
}

.btn-secondary:hover {
  background: var(--academic-primary-light);
  border-color: var(--academic-primary);
  color: var(--academic-primary);
}

.page-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--academic-text-main);
  margin: 0;
  letter-spacing: -0.01em;
}

.page-subtitle {
  font-size: 14px;
  color: var(--academic-text-muted);
  margin: 8px 0 0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

@media (min-width: 900px) {
  .stats-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

.stat-card {
  background: var(--academic-panel);
  border: 1px solid var(--academic-border);
  border-radius: 16px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: all 0.2s;
}

.stat-card:hover {
  border-color: var(--academic-border-hover);
  box-shadow: var(--shadow-soft);
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.status-icon {
  background: rgba(16, 185, 129, 0.1);
  color: #10B981;
}

.redis-icon {
  background: rgba(236, 72, 153, 0.1);
  color: #EC4899;
}

.db-icon {
  background: rgba(59, 130, 246, 0.1);
  color: #3B82F6;
}

.qa-icon {
  background: rgba(139, 92, 246, 0.1);
  color: #8B5CF6;
}

.user-icon {
  background: rgba(59, 130, 246, 0.1);
  color: #3B82F6;
}

.active-icon {
  background: rgba(16, 185, 129, 0.1);
  color: #10B981;
}

.upload-icon {
  background: rgba(37, 99, 235, 0.1);
  color: #2563EB;
}

.parse-icon {
  background: rgba(245, 158, 11, 0.1);
  color: #F59E0B;
}

.stat-content {
  flex: 1;
  min-width: 0;
}

.stat-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--academic-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--academic-text-main);
  margin-top: 4px;
}

.stat-value.healthy {
  color: #10B981;
}

.chart-section {
  padding: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--academic-text-main);
  margin: 0;
}

.chart-container {
  height: 380px;
}
</style>