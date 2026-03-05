import { useState, useCallback, useEffect, useRef } from 'react'
import { FileUploader, UploadedFile } from './components/FileUploader'
import { ProgressTracker } from './components/ProgressTracker'
import { ResultPanel, AnalysisResult } from './components/ResultPanel'
import { SettingsPage } from './components/SettingsPage'
import { HistoryPage } from './components/HistoryPage'

type AppStatus = 'idle' | 'uploading' | 'analyzing' | 'completed' | 'failed'
type PageType = 'main' | 'settings' | 'history'
type ThemeType = 'dark' | 'light'

// 检测 Electron 环境
const isElectron = typeof window !== 'undefined' && (window as any).electronAPI

interface TaskState {
  taskId: string | null
  status: AppStatus
  progress: number
  currentStage: string
  message: string
  result: AnalysisResult | null
  startTime: number | null
  endTime: number | null
}

interface ApiErrorResponse {
  error_code?: string
  message?: string
  detail?: unknown
}

const API_BASE = ''  // Same origin, use proxy in dev

// 分析阶段定义
const ANALYSIS_STAGES = [
  { id: 'material', label: '材料理解' },
  { id: 'strategy', label: '检索策略生成' },
  { id: 'horizontal', label: '横向检索' },
  { id: 'vertical', label: '纵向检索' },
  { id: 'analysis', label: '深度分析' },
  { id: 'report', label: '报告生成' },
]

function App() {
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [userFocus, setUserFocus] = useState('')
  const [taskState, setTaskState] = useState<TaskState>({
    taskId: null,
    status: 'idle',
    progress: 0,
    currentStage: '',
    message: '',
    result: null,
    startTime: null,
    endTime: null,
  })
  const [elapsedTime, setElapsedTime] = useState<number>(0)
  const [currentPage, setCurrentPage] = useState<PageType>('main')
  const [configLoaded, setConfigLoaded] = useState(!isElectron)
  const [theme, setTheme] = useState<ThemeType>('dark')

  const eventSourceRef = useRef<EventSource | null>(null)

  // 初始化主题
  useEffect(() => {
    // 默认深色模式，不读取系统偏好
    document.documentElement.classList.remove('light')
    // 请求浏览器通知权限
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }
  }, [])

  // 切换主题
  const toggleTheme = useCallback(() => {
    setTheme(prev => {
      const newTheme = prev === 'dark' ? 'light' : 'dark'
      if (newTheme === 'light') {
        document.documentElement.classList.add('light')
      } else {
        document.documentElement.classList.remove('light')
      }
      return newTheme
    })
  }, [])

  // Electron 环境下检查配置
  useEffect(() => {
    if (isElectron) {
      (window as any).electronAPI.getConfig().then((config: any) => {
        if (!config.LLM_API_KEY) {
          setCurrentPage('settings')
        }
        setConfigLoaded(true)
      }).catch(() => {
        setCurrentPage('settings')
        setConfigLoaded(true)
      })
    }
  }, [])

  // Update elapsed time during analysis
  useEffect(() => {
    if (taskState.startTime && !taskState.endTime && (taskState.status === 'uploading' || taskState.status === 'analyzing')) {
      const interval = setInterval(() => {
        setElapsedTime(Date.now() - taskState.startTime!)
      }, 100)
      return () => clearInterval(interval)
    }
  }, [taskState.startTime, taskState.endTime, taskState.status])

  const updateTaskState = useCallback((updates: Partial<TaskState>) => {
    setTaskState(prev => ({ ...prev, ...updates }))
  }, [])

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  useEffect(() => {
    return cleanup
  }, [cleanup])

  const readApiError = useCallback(async (response: Response, fallback: string) => {
    try {
      const payload = (await response.json()) as ApiErrorResponse
      return payload.message || fallback
    } catch {
      return fallback
    }
  }, [])

  const handleStartAnalysis = useCallback(async () => {
    if (files.length === 0) {
      alert('请先添加文件或链接')
      return
    }

    cleanup()
    const startTime = Date.now()
    updateTaskState({
      status: 'uploading',
      progress: 0,
      currentStage: '正在上传文件...',
      message: '',
      result: null,
      startTime: startTime,
      endTime: null,
    })

    try {
      // 1. Create task
      const createRes = await fetch(`${API_BASE}/api/tasks`, {
        method: 'POST',
      })
      if (!createRes.ok) {
        throw new Error(await readApiError(createRes, 'Failed to create task'))
      }
      const { task_id } = await createRes.json()

      updateTaskState({ taskId: task_id })

      // 2. Upload files
      const formData = new FormData()
      const urls: string[] = []
      const textContents: string[] = []

      for (const file of files) {
        if (file.type === 'url' && file.url) {
          urls.push(file.url)
        } else if (file.type === 'text' && file.content) {
          textContents.push(file.content)
        } else if (file.file) {
          formData.append('files', file.file)
        }
      }

      if (urls.length > 0) {
        formData.append('urls', urls.join('\n'))
      }

      if (textContents.length > 0) {
        formData.append('text_contents', JSON.stringify(textContents))
      }

      const uploadRes = await fetch(`${API_BASE}/api/upload/${task_id}`, {
        method: 'POST',
        body: formData,
      })
      if (!uploadRes.ok) {
        throw new Error(await readApiError(uploadRes, 'Failed to upload files'))
      }

      // 3. Start analysis
      const analyzeRes = await fetch(`${API_BASE}/api/analyze/${task_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id, user_focus: userFocus || null }),
      })
      if (!analyzeRes.ok) {
        throw new Error(await readApiError(analyzeRes, 'Failed to start analysis'))
      }

      // 不要手动设置 currentStage，让 SSE 完全控制
      updateTaskState({
        status: 'analyzing',
      })

      // 4. Subscribe to SSE for progress
      const eventSource = new EventSource(`${API_BASE}/api/progress/${task_id}`)
      eventSourceRef.current = eventSource

      eventSource.addEventListener('progress', (event) => {
        const data = JSON.parse(event.data)
        updateTaskState({
          progress: data.progress,
          currentStage: data.current_stage,
          message: data.message || '',
        })
      })

      eventSource.addEventListener('completed', (event) => {
        const data = JSON.parse(event.data)
        const title = data.result?.summary?.title || '政策解读报告'
        updateTaskState({
          status: 'completed',
          progress: 100,
          currentStage: '完成',
          result: data.result,
          endTime: Date.now(),
        })
        cleanup()
        // 浏览器通知
        if ('Notification' in window && Notification.permission === 'granted') {
          new Notification('✅ 分析完成', {
            body: title,
            icon: '/favicon.ico',
          })
        }
      })

      eventSource.addEventListener('failed', (event) => {
        const data = JSON.parse(event.data)
        const failureMessage = data?.error?.message || data?.result?.error || '分析失败'
        updateTaskState({
          status: 'failed',
          currentStage: '失败',
          message: failureMessage,
          result: data.result || { task_id, success: false, error: failureMessage },
          endTime: Date.now(),
        })
        cleanup()
        // 浏览器通知
        if ('Notification' in window && Notification.permission === 'granted') {
          new Notification('❌ 分析失败', {
            body: failureMessage,
            icon: '/favicon.ico',
          })
        }
      })

      eventSource.addEventListener('error', () => {
        fetch(`${API_BASE}/api/tasks/${task_id}`)
          .then(res => res.json())
          .then(data => {
            if (data.status === 'completed') {
              updateTaskState({
                status: 'completed',
                progress: 100,
                currentStage: '完成',
                result: data.result,
              })
            } else if (data.status === 'failed') {
              const failureMessage = data?.error?.message || data.message || data?.result?.error || '分析失败'
              updateTaskState({
                status: 'failed',
                message: failureMessage,
                result: data.result || { task_id, success: false, error: failureMessage },
              })
            }
          })
          .catch(() => {
            updateTaskState({
              status: 'failed',
              message: '连接已断开',
            })
          })
        cleanup()
      })

    } catch (error) {
      console.error('Analysis error:', error)

      let errorMessage = '未知错误'
      if (error instanceof Error) {
        const msg = error.message.toLowerCase()
        if (msg.includes('failed to fetch') || msg.includes('network')) {
          errorMessage = '网络连接失败，请检查后端服务是否运行'
        } else if (msg.includes('failed to create task')) {
          errorMessage = '创建任务失败，请重试'
        } else if (msg.includes('failed to upload')) {
          errorMessage = '文件上传失败，请检查文件格式是否正确'
        } else if (msg.includes('failed to start analysis')) {
          errorMessage = '启动分析失败，请重试'
        } else if (msg.includes('api key') || msg.includes('unauthorized')) {
          errorMessage = 'API 密钥配置错误，请检查 .env 文件'
        } else if (msg.includes('timeout')) {
          errorMessage = '请求超时，请稍后重试'
        } else {
          errorMessage = error.message
        }
      }

      updateTaskState({
        status: 'failed',
        message: errorMessage,
        currentStage: '失败',
      })
    }
  }, [files, cleanup, updateTaskState, readApiError])

  const handleReset = useCallback(() => {
    cleanup()
    setFiles([])
    setUserFocus('')
    setTaskState({
      taskId: null,
      status: 'idle',
      progress: 0,
      currentStage: '',
      message: '',
      result: null,
      startTime: null,
      endTime: null,
    })
  }, [cleanup])

  // 状态判断
  const isProcessing = taskState.status === 'uploading' || taskState.status === 'analyzing'
  const showProgress = taskState.status !== 'idle'
  const showResult = taskState.status === 'completed' || taskState.status === 'failed'

  // 加载中状态
  if (!configLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-accent-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p style={{ color: 'var(--text-secondary)' }}>加载中...</p>
        </div>
      </div>
    )
  }

  // 设置页面
  if (currentPage === 'settings') {
    return (
      <SettingsPage
        onSave={() => setCurrentPage('main')}
        onCancel={configLoaded ? () => setCurrentPage('main') : undefined}
        isFirstTime={!configLoaded}
      />
    )
  }

  // 历史记录页面
  if (currentPage === 'history') {
    return (
      <HistoryPage
        onBack={() => setCurrentPage('main')}
        baseUrl={API_BASE}
      />
    )
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Header - 玻璃态效果 */}
      <header className="glass sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo & 标题 */}
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg" style={{ backgroundColor: 'rgba(220, 38, 38, 0.15)' }}>
                <svg className="w-6 h-6 text-accent-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div>
                <h1 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  中国政治解读分析
                </h1>
                <p className="text-xs hidden sm:block" style={{ color: 'var(--text-muted)' }}>
                  多维度证据驱动的深度解读
                </p>
              </div>
            </div>

            {/* 右侧按钮 */}
            <div className="flex items-center gap-2">
              {/* 主题切换 */}
              <button
                onClick={toggleTheme}
                className="p-2 rounded-lg transition-colors"
                style={{
                  color: 'var(--text-secondary)',
                  backgroundColor: 'transparent'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--border-color)'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                title={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
              >
                {theme === 'dark' ? (
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                  </svg>
                )}
              </button>

              {/* 历史记录按钮 */}
              <button
                onClick={() => setCurrentPage('history')}
                className="p-2 rounded-lg transition-colors"
                style={{
                  color: 'var(--text-secondary)',
                  backgroundColor: 'transparent'
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--border-color)'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                title="历史记录"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </button>

              {/* 设置按钮 (Electron) */}
              {isElectron && (
                <button
                  onClick={() => setCurrentPage('settings')}
                  className="p-2 rounded-lg transition-colors"
                  style={{
                    color: 'var(--text-secondary)',
                    backgroundColor: 'transparent'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--border-color)'}
                  onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                  title="设置"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </button>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content - 渐进式三栏布局 */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="flex flex-col lg:flex-row gap-6 h-full">

          {/* 左侧 - 上传区 */}
          <div
            className={`transition-all duration-300 ease-out ${showProgress ? 'lg:w-72' : 'lg:w-80'
              } flex-shrink-0`}
          >
            <div className="card p-5 h-full">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                  style={{ backgroundColor: 'rgba(220, 38, 38, 0.15)' }}>
                  <svg className="w-4 h-4 text-accent-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                  </svg>
                </div>
                <h2 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                  上传材料
                </h2>
              </div>

              <p className="text-sm mb-4" style={{ color: 'var(--text-muted)' }}>
                支持新闻/政策链接、图片、PDF文件
              </p>

              <FileUploader
                files={files}
                onFilesChange={setFiles}
                disabled={isProcessing}
              />

              {/* 政策解读重点（可选） */}
              <details className="mt-3" style={{ color: 'var(--text-secondary)' }}>
                <summary className="cursor-pointer text-sm flex items-center gap-1 select-none" style={{ color: 'var(--text-muted)' }}>
                  📌 政策解读重点（可选）
                </summary>
                <textarea
                  value={userFocus}
                  onChange={(e) => setUserFocus(e.target.value)}
                  disabled={isProcessing}
                  placeholder="请输入您希望 AI 重点分析的方向，例如：请对比本次领导分工与上次公布的异同，重点分析人事变动背后的信号…"
                  rows={3}
                  className="mt-2 w-full rounded-lg text-sm resize-none"
                  style={{
                    background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border-primary)',
                    color: 'var(--text-primary)',
                    padding: '8px 12px',
                    outline: 'none',
                  }}
                />
              </details>

              {/* 开始按钮 */}
              <div className="mt-4 flex gap-2">
                <button
                  onClick={handleStartAnalysis}
                  disabled={files.length === 0 || isProcessing}
                  className="btn-primary flex-1 flex items-center justify-center gap-2"
                >
                  {isProcessing ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      处理中...
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      开始解读
                    </>
                  )}
                </button>

                {showResult && (
                  <button
                    onClick={handleReset}
                    className="btn-secondary px-4"
                    title="重新开始"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* 中间 - 进度区 (渐进显示) */}
          {showProgress && (
            <div className="lg:w-64 flex-shrink-0 animate-slide-in-right">
              <div className="card p-5 h-full">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ backgroundColor: 'rgba(0, 212, 170, 0.15)' }}>
                    {taskState.status === 'completed' ? (
                      <svg className="w-4 h-4 text-tech-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : taskState.status === 'failed' ? (
                      <svg className="w-4 h-4 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    ) : (
                      <svg className="w-4 h-4 text-tech-500 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                    )}
                  </div>
                  <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {taskState.status === 'completed' ? '分析完成' :
                      taskState.status === 'failed' ? '分析失败' : '分析进度'}
                  </h3>
                </div>

                <ProgressTracker
                  stages={ANALYSIS_STAGES}
                  currentStage={taskState.currentStage}
                  status={taskState.status}
                  message={taskState.message}
                  elapsedTime={elapsedTime}
                />
              </div>
            </div>
          )}

          {/* 右侧 - 报告区/占位区 */}
          <div className="flex-1 min-w-0">
            {showResult ? (
              <div className="animate-slide-in-right">
                <ResultPanel
                  result={taskState.result}
                  baseUrl={API_BASE}
                  duration={taskState.startTime && taskState.endTime ? taskState.endTime - taskState.startTime : null}
                  status={taskState.status}
                  message={taskState.message}
                />
              </div>
            ) : showProgress ? (
              /* 等待报告生成 */
              <div className="card p-8 h-full flex flex-col items-center justify-center text-center animate-fade-in">
                <div className="w-16 h-16 rounded-full flex items-center justify-center mb-4"
                  style={{ backgroundColor: 'rgba(220, 38, 38, 0.1)' }}>
                  <svg className="w-8 h-8 text-accent-500 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <h3 className="font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
                  报告生成中
                </h3>
                <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                  分析完成后将在此处显示报告摘要
                </p>
              </div>
            ) : (
              /* 空闲状态占位 */
              <div className="card p-8 h-full flex flex-col items-center justify-center text-center">
                <div className="w-20 h-20 rounded-full flex items-center justify-center mb-4"
                  style={{ backgroundColor: 'rgba(100, 116, 139, 0.1)' }}>
                  <svg className="w-10 h-10" style={{ color: 'var(--text-muted)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <h3 className="font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>
                  等待分析
                </h3>
                <p className="text-sm max-w-xs" style={{ color: 'var(--text-muted)' }}>
                  上传政策文件、新闻链接或文本内容，点击"开始解读"生成多维度分析报告
                </p>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="py-4" style={{ borderTop: '1px solid var(--border-color)' }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-center text-xs" style={{ color: 'var(--text-muted)' }}>
            中国政治解读分析系统 · 证据驱动的政策深度解读
          </p>
        </div>
      </footer>
    </div>
  )
}

export default App
