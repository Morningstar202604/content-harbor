import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'
import { api } from '@/api'

/** 标签治理 */
export const useTagStore = defineStore('tag', {
  state: () => ({
    tags: [],
  }),

  actions: {
    async loadTags(limit = 50) { this.tags = await api.tags(limit) },
    async syncTags() {
      const r = await api.syncTags()
      ElMessage.success(`标签重新统计完成：${r.synced} 个标签`)
      return r
    },
    async renameTag(oldName, newName) {
      const r = await api.renameTag(oldName, newName)
      ElMessage.success(`已将「${oldName}」重命名为「${newName}」（影响 ${r.affected} 篇文章）`)
      return r
    },
    async mergeTag(from, to) {
      const r = await api.mergeTag(from, to)
      ElMessage.success(`已合并「${from}」→「${to}」（影响 ${r.affected} 篇文章）`)
      return r
    },
    async suggestTags(title, contentMd) { return await api.suggestTags(title, contentMd) },
  }
})
