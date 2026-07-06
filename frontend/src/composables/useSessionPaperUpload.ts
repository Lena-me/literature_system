import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { papersApi } from '@/api/papers'
import { useNotebookStore } from '@/stores/notebook'
import { usePaperStore } from '@/stores/papers'

export function useSessionPaperUpload() {
  const notebook = useNotebookStore()
  const paperStore = usePaperStore()
  const uploading = ref(false)
  const uploadChip = ref<{ filename: string; status: string } | null>(null)

  async function uploadLocalFiles(files: FileList | File[]): Promise<number[]> {
    const fileList = Array.from(files)
    if (!fileList.length) return []

    const targetSessionId = notebook.activeSessionId
    if (!targetSessionId) {
      ElMessage.warning('请先创建或选择一个会话')
      return []
    }

    const uploadedIds: number[] = []
    for (const file of fileList) {
      if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
        ElMessage.warning(`${file.name} 不是 PDF 文件，已跳过`)
        continue
      }

      uploading.value = true
      uploadChip.value = { filename: file.name, status: '上传中...' }
      try {
        const paper = await papersApi.upload(file)
        uploadedIds.push(paper.id)
        paperStore.applyParseUpdate({
          id: paper.id,
          parse_status: paper.parse_status,
          title: paper.title || paper.original_filename,
        })
        uploadChip.value = { filename: file.name, status: '解析中...' }
        await notebook.addSources([paper.id], targetSessionId)
        paperStore.ensureParseSync()
      } catch (e: any) {
        const msg = e?.response?.data?.detail || e?.message || '上传失败'
        ElMessage.error(`${file.name}: ${msg}`)
      }
    }

    uploading.value = false
    uploadChip.value = null

    if (uploadedIds.length > 0) {
      ElMessage.success(`已上传并挂载 ${uploadedIds.length} 篇文献`)
    }

    return uploadedIds
  }

  async function onFileInputChange(e: Event): Promise<number[]> {
    const input = e.target as HTMLInputElement
    const files = input.files
    if (!files?.length) return []
    const ids = await uploadLocalFiles(files)
    input.value = ''
    return ids
  }

  return {
    uploading,
    uploadChip,
    uploadLocalFiles,
    onFileInputChange,
  }
}
