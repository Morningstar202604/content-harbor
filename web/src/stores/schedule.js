import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import { api } from '@/api'

/** 定时发布调度器 */
export const useScheduleStore = defineStore('schedule', {
  state: () => ({
    schedules: [],
  }),

  actions: {
    async loadSchedules() { this.schedules = await api.schedules(true) || [] },
    async createSchedule(data) {
      const r = await api.createSchedule(data)
      ElMessage.success(`定时任务已创建（#${r.id}）`)
      await this.loadSchedules()
      return r
    },
    async updateSchedule(sid, data) {
      const r = await api.updateSchedule(sid, data)
      await this.loadSchedules()
      return r
    },
    async pauseSchedule(sid) { await api.pauseSchedule(sid); ElMessage.success('已暂停'); await this.loadSchedules() },
    async resumeSchedule(sid) { await api.resumeSchedule(sid); ElMessage.success('已启用'); await this.loadSchedules() },
    async triggerSchedule(sid) { await api.triggerSchedule(sid); ElMessage.success('已触发执行'); await this.loadSchedules() },
    async deleteSchedule(sid) { await api.deleteSchedule(sid); ElMessage.success('已删除'); await this.loadSchedules() },
  }
})
