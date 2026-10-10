import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import { api } from '@/api'

/** Webhook / 事件通知 */
export const useWebhookStore = defineStore('webhook', {
  state: () => ({
    webhooks: [],
    notifications: [],
  }),

  actions: {
    async loadWebhooks() { this.webhooks = await api.webhooks() || [] },
    async createWebhook(data) {
      const r = await api.createWebhook(data)
      ElMessage.success('Webhook 注册成功')
      await this.loadWebhooks()
      return r
    },
    async updateWebhook(wid, data) { await api.updateWebhook(wid, data); await this.loadWebhooks() },
    async deleteWebhook(wid) { await api.deleteWebhook(wid); ElMessage.success('已删除'); await this.loadWebhooks() },
    async testWebhook(wid) { await api.testWebhook(wid); ElMessage.success('测试事件已发送') },
    async loadNotifications() { this.notifications = await api.notifications() || [] },
  }
})
