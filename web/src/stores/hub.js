import { defineStore } from 'pinia'
import { ElNotification } from 'element-plus'
import { api } from '@/api'

// 子 store：按领域拆分
import { useArticleStore } from './article'
import { useTaskStore } from './task'
import { useAccountStore } from './account'
import { useTagStore } from './tag'
import { useScheduleStore } from './schedule'
import { useWebhookStore } from './webhook'

/**
 *主编排层：组合所有子 store，对外提供统一接口。
 * 组件可以直接用 useHubStore()（兼容旧代码），
 * 也可以直接用各子 store（推荐新代码）。
 */
export const useHubStore = defineStore('hub', {
  state: () => ({
    view: localStorage.getItem('hub_view') || 'write',
    aiReady: false,
    aiProviders: [],
    publishing: false,
  }),

  getters: {
    articles() { return useArticleStore().articles },
    currentId() { return useArticleStore().currentId },
    current() { return useArticleStore().current },
    publications() { return useArticleStore().publications },
    allPubs() { return useArticleStore().allPubs },
    keyword() { return useArticleStore().keyword },
    filterStatus() { return useArticleStore().filterStatus },
    dirty() { return useArticleStore().dirty },
    saving() { return useArticleStore().saving },
    loadingList() { return useArticleStore().loadingList },
    filtered() { return useArticleStore().filtered },
    updatable() { return useArticleStore().updatable },

    platforms() { return useAccountStore().platforms },
    accounts() { return useAccountStore().accounts },
    stats() { return useAccountStore().stats },
    pendingHuman() { return useAccountStore().pendingHuman },

    tasks() { return useTaskStore().tasks },
    loginTasks() { return useTaskStore().loginTasks },
    waitingTasks() { return useTaskStore().waitingTasks },

    tags() { return useTagStore().tags },
    schedules() { return useScheduleStore().schedules },
    webhooks() { return useWebhookStore().webhooks },
    notifications() { return useWebhookStore().notifications },
  },

  actions: {
    switchView(v) {
      this.view = v
      localStorage.setItem('hub_view', v)
    },

    async boot() {
      const account = useAccountStore()
      const task = useTaskStore()
      const article = useArticleStore()

      await Promise.all([
        account.loadStatus(),
        account.loadPlatforms(),
        article.loadList(),
        account.loadPendingHuman(),
        task.loadTasks(),
      ])

      task.connectSSE()

      try { this.aiReady = (await api.aiStatus()).ready } catch { this.aiReady = false }

      this._phTimer && clearInterval(this._phTimer)
      this._phTimer = setInterval(() => {
        account.loadPendingHuman(true)
        task.loadTasks(true)
      }, 30000)
    },

    dispose() {
      if (this._phTimer) { clearInterval(this._phTimer); this._phTimer = null }
      useTaskStore().disconnectSSE()
    },

    newArticle() { return useArticleStore().newArticle() },
    async save() { return await useArticleStore().save() },
    async open(id) { return await useArticleStore().open(id) },
    async loadPubs() { return await useArticleStore().loadPubs() },
    async loadAllPubs() { return await useArticleStore().loadAllPubs() },
    async loadStatus() { return await useAccountStore().loadStatus() },
    async loadPlatforms() { return await useAccountStore().loadPlatforms() },
    async loadPendingHuman(notify) { return await useAccountStore().loadPendingHuman(notify) },
    async loadTasks(notify) { return await useTaskStore().loadTasks(notify) },

    async startLogin(platform) { return await useTaskStore().startLogin(platform) },
    async resumeTask(taskId, approved) { return await useTaskStore().resumeTask(taskId, approved) },

    async loadAiProviders() {
      try { this.aiProviders = await api.aiProviders() || [] }
      catch { return [] }
    },

    async publish(platforms, draftOnly, settings = {}) {
      const article = useArticleStore()
      const account = useAccountStore()
      if (!platforms.length) return null
      if (!article.currentId) await article.save()
      if (!article.currentId) return null

      this.publishing = true
      try {
        const t = await api.publish(article.currentId, platforms, draftOnly, 'default', settings)
        const done = await useTaskStore()._waitTask(t.task_id, 600000)
        await Promise.all([
          account.loadPendingHuman(true),
          account.loadStatus(),
          account.loadPlatforms(),
          article.loadPubs(),
          article.loadAllPubs(),
          aiLoadTasks(),
        ])
        return done
      } finally { this.publishing = false }
    },

    async updateRemote(platforms) {
      const article = useArticleStore()
      const account = useAccountStore()
      if (!article.currentId) return
      this.publishing = true
      try {
        const t = await api.update(article.currentId, platforms)
        const done = await useTaskStore()._waitTask(t.task_id, 900000)
        await Promise.all([account.loadStatus(), article.loadPubs(), article.loadAllPubs(), aiLoadTasks()])
        return done
      } finally { this.publishing = false }
    },

    async syncPending() {
      const account = useAccountStore()
      const article = useArticleStore()
      const t = await api.syncPending()
      const done = await useTaskStore()._waitTask(t.task_id, 900000)
      await Promise.all([account.loadStatus(), article.loadPubs(), aiLoadTasks()])
      return done
    },

    async refreshPlatform(pf) {
      const article = useArticleStore()
      const t = await api.refresh(pf)
      const done = await useTaskStore()._waitTask(t.task_id, 300000)
      await Promise.all([article.loadList(), aiLoadTasks()])
      return done
    },

    async assistOpen(platform, url) {
      if (!url) { ElMessage.warning('没有可打开的平台页地址'); return }
      const t = await api.assistOpen(platform, url)
      ElMessage.success('已在内置浏览器打开平台页（带登录态）——完成操作后任务自动结束')
    },

    // AI
    aiTranslate(...a) { return useArticleStore().aiTranslate(...a) },
    aiImagePrompts(...a) { return useArticleStore().aiImagePrompts(...a) },
    aiOutline(...a) { return useArticleStore().aiOutline(...a) },
    aiSeo(...a) { return useArticleStore().aiSeo(...a) },
    cloneArticle(...a) { return useArticleStore().cloneArticle(...a) },
    // 版本
    loadVersions(...a) { return useArticleStore().loadVersions(...a) },
    rollbackVersion(...a) { return useArticleStore().rollbackVersion(...a) },
    versionDiff(...a) { return useArticleStore().versionDiff(...a) },
    // 质检
    qaArticle(...a) { return useArticleStore().qaArticle(...a) },
    qaAnalyze(...a) { return useArticleStore().qaAnalyze(...a) },
    // 标签
    loadTags(...a) { return useTagStore().loadTags(...a) },
    syncTags(...a) { return useTagStore().syncTags(...a) },
    renameTag(...a) { return useTagStore().renameTag(...a) },
    mergeTag(...a) { return useTagStore().mergeTag(...a) },
    suggestTags(...a) { return useTagStore().suggestTags(...a) },
    // 定时任务
    loadSchedules(...a) { return useScheduleStore().loadSchedules(...a) },
    createSchedule(...a) { return useScheduleStore().createSchedule(...a) },
    updateSchedule(...a) { return useScheduleStore().updateSchedule(...a) },
    pauseSchedule(...a) { return useScheduleStore().pauseSchedule(...a) },
    resumeSchedule(...a) { return useScheduleStore().resumeSchedule(...a) },
    triggerSchedule(...a) { return useScheduleStore().triggerSchedule(...a) },
    deleteSchedule(...a) { return useScheduleStore().deleteSchedule(...a) },
    // Webhook
    loadWebhooks(...a) { return useWebhookStore().loadWebhooks(...a) },
    createWebhook(...a) { return useWebhookStore().createWebhook(...a) },
    updateWebhook(...a) { return useWebhookStore().updateWebhook(...a) },
    deleteWebhook(...a) { return useWebhookStore().deleteWebhook(...a) },
    testWebhook(...a) { return useWebhookStore().testWebhook(...a) },
    loadNotifications(...a) { return useWebhookStore().loadNotifications(...a) },
  }
})

import { ElMessage } from 'element-plus'

async function aiLoadTasks() {
  try { await useTaskStore().loadTasks(true) } catch { /* 静默 */ }
}
