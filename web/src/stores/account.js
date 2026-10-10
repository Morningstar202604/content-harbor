import { defineStore } from 'pinia'
import { api } from '@/api'

/** 平台账号、登录态管理 */
export const useAccountStore = defineStore('account', {
  state: () => ({
    platforms: [],
    accounts: [],
    stats: {},
    pendingHuman: [],
  }),

  actions: {
    async loadStatus() {
      this.stats = await api.status()
      this.accounts = this.stats.accounts || []
    },
    async loadPlatforms() {
      this.platforms = await api.platforms()
    },
    async checkAccount(platform, account = 'default') {
      return await api.checkAccount(platform, account)
    },
    async loadPendingHuman(notify = false) {
      try {
        const list = await api.pendingHuman() || []
        const prevIds = new Set(this.pendingHuman.map(x => x.platform + x.post_id + x.article_id))
        this.pendingHuman = list
        if (notify) {
          const fresh = list.filter(x => !prevIds.has(x.platform + x.post_id + x.article_id))
          // 通知由 hub store 统一弹，避免分散
          return fresh.length
        }
        return 0
      } catch { return 0 }
    },
  }
})
