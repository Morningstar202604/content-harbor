import { ref, computed } from 'vue'
import { ElNotification, ElMessage } from 'element-plus'
import { useHubStore } from '@/stores/hub'

// 平台首字母 badge
const PLAT_MARKS = {
  zhihu: '知', bilibili: 'B', cnblogs: '博', csdn: 'C', metaweblog: '站',
  juejin: '掘', oschina: '开', segmentfault: '思', toutiao: '头'
}

// 平台可选分类选项
const CAT_OPTIONS = {
  juejin: ['后端', '前端', 'android', 'ios', '人工智能', '开发工具', '代码人生', '阅读'],
  csdn: ['后端与架构设计', '前端开发', '移动开发', '人工智能', '网络安全', '云计算', '大数据', '物联网', '数据库', '运维', '程序人生', '其他'],
}

const CAT_MEM_KEY = 'harbor.publish.categories'

// 分类记忆：记住上次选的分类，下次打开发布面板自动带出
function loadCatMem() {
  try { return JSON.parse(localStorage.getItem(CAT_MEM_KEY) || '{}') } catch { return {} }
}

function saveCatMem(settings) {
  try {
    const mem = {}
    for (const id of Object.keys(settings)) {
      const cat = settings[id]?.category
      if (cat) mem[id] = cat
    }
    localStorage.setItem(CAT_MEM_KEY, JSON.stringify(mem))
  } catch { /* 隐私模式等场景静默失败 */ }
}

function ensureCfg(id, platformSettings) {
  if (!platformSettings.value[id]) {
    const cat = loadCatMem()[id] || ''
    platformSettings.value[id] = { category: cat, tags: '' }
  }
}

/**
 * 发布面板逻辑 composable：平台选择、分类/标签配置、登录状态、进度追踪。
 * PublishWizard / ManagePanel 等有发布能力的组件都可以复用。
 */
export function usePublishWizard(platforms) {
  const hub = useHubStore()

  const selected = ref([])
  const draftOnly = ref(false)
  const running = ref(false)
  const done = ref(false)
  const results = ref([])
  const platformSettings = ref({})
  const cfgOpen = ref(null)  // 当前展开配置的平台 ID

  const mark = p => PLAT_MARKS[p.id] || p.name?.[0] || '?'
  const catOptions = CAT_OPTIONS

  const progressPct = computed(() => {
    if (!selected.value.length) return running.value ? 15 : 0
    return Math.min(95, Math.round(results.value.length / selected.value.length * 100))
  })

  // 分类一改就记
  function rememberCategory() {
    saveCatMem(platformSettings.value)
  }

  function toggleCfg(id) {
    if (cfgOpen.value === id) { cfgOpen.value = null; return }
    cfgOpen.value = id
    ensureCfg(id, platformSettings)
  }

  function toggle(id) {
    const i = selected.value.indexOf(id)
    i >= 0 ? selected.value.splice(i, 1) : selected.value.push(id)
  }

  function selectAll() {
    selected.value = platforms.map(p => p.id)
  }

  function clearAll() {
    selected.value = []
  }

  function reset() {
    running.value = false
    done.value = false
    results.value = []
    selected.value = []
    platformSettings.value = {}
    cfgOpen.value = null
  }

  async function runPublish(onDone) {
    if (!selected.value.length) {
      ElMessage.warning('先选要发到哪些平台')
      return null
    }
    running.value = true
    done.value = false
    results.value = []
    try {
      const t = await hub.publish(selected.value.slice(), draftOnly.value, platformSettings.value)
      if (!t) return null
      const res = t.result || {}
      results.value = Array.isArray(res) ? res : (res.results || [])
      for (const r of results.value) {
        if (r.ok && r.warning) {
          ElNotification({
            title: `${r.platform} 需要人工收尾`,
            message: (r.warning || '').slice(0, 120),
            type: 'warning', duration: 0
          })
        }
      }
      await hub.loadPendingHuman()
      if (results.value.length && onDone) onDone(results.value)
      return results.value
    } catch (e) {
      results.value = []
      ElMessage.error(e?.response?.data?.detail || e?.message || '发布失败，请查看任务记录')
      return null
    } finally {
      running.value = false
    }
  }

  return {
    selected, draftOnly, running, done, results, platformSettings, cfgOpen,
    progressPct, catOptions, mark,
    toggle, toggleCfg, selectAll, clearAll, reset, rememberCategory, runPublish
  }
}
