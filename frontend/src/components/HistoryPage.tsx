import { useState, useEffect, useCallback } from 'react'

interface TaskSummary {
  task_id: string
  status: string
  progress: number
  created_at: string
  title?: string
}

interface HistoryPageProps {
  onBack: () => void
  baseUrl: string
}

export function HistoryPage({ onBack, baseUrl }: HistoryPageProps) {
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const fetchTasks = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${baseUrl}/api/tasks`)
      if (!res.ok) throw new Error('获取任务列表失败')
      const data = await res.json()
      setTasks(data.tasks || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : '未知错误')
    } finally {
      setLoading(false)
    }
  }, [baseUrl])

  useEffect(() => {
    fetchTasks()
  }, [fetchTasks])

  const handleDelete = useCallback(async (taskId: string) => {
    if (!confirm(`确认删除任务 ${taskId}？相关文件也会被清理。`)) return
    setDeletingId(taskId)
    try {
      const res = await fetch(`${baseUrl}/api/tasks/${taskId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('删除失败')
      setTasks(prev => prev.filter(t => t.task_id !== taskId))
    } catch (e) {
      alert(e instanceof Error ? e.message : '删除失败')
    } finally {
      setDeletingId(null)
    }
  }, [baseUrl])

  const handleDownload = useCallback((taskId: string, format: 'html' | 'pdf', title?: string) => {
    const safeName = (title || '政策解读报告').replace(/[/\\?%*:|"<>]/g, '_').slice(0, 80)
    const serverFilename = format === 'html' ? 'policy-brief.html' : 'policy-brief.pdf'
    // 通过创建隐藏 a 标签来指定下载文件名
    const link = document.createElement('a')
    link.href = `${baseUrl}/api/download/${taskId}/${serverFilename}`
    link.download = `${safeName}.${format}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [baseUrl])

  const statusBadge = (status: string) => {
    const styles: Record<string, { bg: string; text: string; label: string }> = {
      completed: { bg: 'rgba(34, 197, 94, 0.15)', text: '#22c55e', label: '✅ 完成' },
      running: { bg: 'rgba(59, 130, 246, 0.15)', text: '#3b82f6', label: '⏳ 运行中' },
      failed: { bg: 'rgba(239, 68, 68, 0.15)', text: '#ef4444', label: '❌ 失败' },
      pending: { bg: 'rgba(156, 163, 175, 0.15)', text: '#9ca3af', label: '⏸ 等待' },
    }
    const s = styles[status] || styles.pending
    return (
      <span style={{
        display: 'inline-block',
        padding: '2px 10px',
        borderRadius: '9999px',
        fontSize: '0.75rem',
        fontWeight: 600,
        backgroundColor: s.bg,
        color: s.text,
      }}>
        {s.label}
      </span>
    )
  }

  const formatDate = (iso: string) => {
    try {
      const d = new Date(iso)
      return d.toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit',
      })
    } catch {
      return iso
    }
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Header */}
      <header className="glass sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <button
                onClick={onBack}
                className="p-2 rounded-lg transition-colors"
                style={{ color: 'var(--text-secondary)', backgroundColor: 'transparent' }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--border-color)'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
              </button>
              <div>
                <h1 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  历史分析记录
                </h1>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  共 {tasks.length} 条记录
                </p>
              </div>
            </div>

            <button
              onClick={fetchTasks}
              className="p-2 rounded-lg transition-colors"
              style={{ color: 'var(--text-secondary)', backgroundColor: 'transparent' }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--border-color)'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
              title="刷新"
            >
              <svg className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {loading && tasks.length === 0 ? (
          <div className="card p-8 text-center">
            <div className="w-8 h-8 border-2 border-accent-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p style={{ color: 'var(--text-secondary)' }}>加载中...</p>
          </div>
        ) : error ? (
          <div className="card p-8 text-center">
            <p style={{ color: '#ef4444' }}>⚠️ {error}</p>
            <button onClick={fetchTasks} className="btn-secondary mt-4">重试</button>
          </div>
        ) : tasks.length === 0 ? (
          <div className="card p-12 text-center">
            <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4"
              style={{ backgroundColor: 'rgba(100, 116, 139, 0.1)' }}>
              <svg className="w-8 h-8" style={{ color: 'var(--text-muted)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <h3 className="font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>暂无历史记录</h3>
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>完成第一次分析后，记录将出现在这里</p>
          </div>
        ) : (
          <div className="space-y-3">
            {tasks.map((task) => (
              <div key={task.task_id} className="card p-4 flex items-center justify-between gap-4">
                {/* Left: info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <span className="font-medium text-sm truncate" style={{ color: 'var(--text-primary)', maxWidth: '400px' }}>
                      {task.title || task.task_id}
                    </span>
                    {statusBadge(task.status)}
                  </div>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {formatDate(task.created_at)}
                    {task.title && (
                      <span style={{ marginLeft: 12 }}>ID: {task.task_id}</span>
                    )}
                    {task.status === 'running' && task.progress > 0 && (
                      <span style={{ marginLeft: 12, color: '#3b82f6' }}>
                        进度 {task.progress}%
                      </span>
                    )}
                  </p>
                </div>

                {/* Right: actions */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  {task.status === 'completed' && (
                    <>
                      <button
                        onClick={() => handleDownload(task.task_id, 'html', task.title)}
                        className="btn-secondary text-xs px-3 py-1.5"
                        title="下载 HTML 报告"
                      >
                        HTML
                      </button>
                      <button
                        onClick={() => handleDownload(task.task_id, 'pdf', task.title)}
                        className="btn-secondary text-xs px-3 py-1.5"
                        title="下载 PDF 报告"
                      >
                        PDF
                      </button>
                    </>
                  )}
                  <button
                    onClick={() => handleDelete(task.task_id)}
                    disabled={deletingId === task.task_id}
                    className="p-1.5 rounded-lg transition-colors"
                    style={{ color: 'var(--text-muted)', backgroundColor: 'transparent' }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.15)'
                      e.currentTarget.style.color = '#ef4444'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = 'transparent'
                      e.currentTarget.style.color = 'var(--text-muted)'
                    }}
                    title="删除"
                  >
                    {deletingId === task.task_id ? (
                      <div className="w-4 h-4 border-2 border-red-400 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
