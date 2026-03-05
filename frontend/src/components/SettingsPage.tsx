import { useState, useEffect } from 'react'

// 配置接口
interface Config {
  LLM_API_URL: string
  LLM_API_KEY: string
  LLM_MODEL: string
  TAVILY_API_KEY: string
}

// 模型选项
const MODEL_OPTIONS = [
  { value: 'gemini-3-flash-preview', label: 'Gemini 3 Flash (推荐)' },
  { value: 'gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro' },
  { value: 'glm-5', label: 'GLM-5 (智谱)' },
  { value: 'kimi-k2.5', label: 'Kimi K2.5 (月之暗面)' },
]

// 默认配置
const DEFAULT_CONFIG: Config = {
  LLM_API_URL: 'https://generativelanguage.googleapis.com/v1beta',
  LLM_API_KEY: '',
  LLM_MODEL: 'gemini-3-flash-preview',
  TAVILY_API_KEY: '',
}

interface SettingsPageProps {
  onSave: () => void
  onCancel?: () => void
  isFirstTime?: boolean
}

export function SettingsPage({ onSave, onCancel, isFirstTime = false }: SettingsPageProps) {
  const [config, setConfig] = useState<Config>(DEFAULT_CONFIG)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 检测 Electron 环境
  const isElectron = typeof window !== 'undefined' && (window as any).electronAPI

  // 加载配置
  useEffect(() => {
    async function loadConfig() {
      if (isElectron) {
        try {
          const savedConfig = await (window as any).electronAPI.getConfig()
          setConfig({
            ...DEFAULT_CONFIG,
            ...savedConfig,
          })
        } catch (e) {
          console.error('Failed to load config:', e)
        }
      }
      setLoading(false)
    }
    loadConfig()
  }, [isElectron])

  // 保存配置
  const handleSave = async () => {
    // 验证必填项
    if (!config.LLM_API_KEY.trim()) {
      setError('请填写 LLM API Key')
      return
    }
    if (!config.TAVILY_API_KEY.trim()) {
      setError('请填写 Tavily API Key')
      return
    }

    setError(null)
    setSaving(true)

    try {
      if (isElectron) {
        // 保存到 Electron 配置文件
        const saveResult = await (window as any).electronAPI.saveConfig({
          LLM_API_URL: config.LLM_API_URL,
          LLM_API_KEY: config.LLM_API_KEY,
          LLM_MODEL: config.LLM_MODEL,
          LLM_PROVIDER: 'openai',  // 使用 OpenAI 格式
          TAVILY_API_KEY: config.TAVILY_API_KEY,
          SEARCH_API_PROVIDER: 'tavily',
        })
        if (!saveResult?.success) {
          throw new Error(saveResult?.error || '配置保存后后端重启失败')
        }
      }
      onSave()
    } catch (e) {
      console.error('Failed to save config:', e)
      setError('保存配置失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  // 更新配置字段
  const updateConfig = (key: keyof Config, value: string) => {
    setConfig(prev => ({ ...prev, [key]: value }))
    setError(null)
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-slate-500 dark:text-slate-400">加载配置中...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      {/* Header */}
      <header className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-700 sticky top-0 z-50">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary-100 dark:bg-primary-900/50">
                <svg className="w-6 h-6 text-primary-600 dark:text-primary-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </div>
              <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">
                {isFirstTime ? '初始配置' : '设置'}
              </h1>
            </div>
            {!isFirstTime && onCancel && (
              <button
                onClick={onCancel}
                className="text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              >
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {isFirstTime && (
          <div className="mb-6 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
            <div className="flex gap-3">
              <svg className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="text-sm text-blue-700 dark:text-blue-300 font-medium">首次使用需要配置 API 密钥</p>
                <p className="text-sm text-blue-600 dark:text-blue-400 mt-1">
                  请填写下方必填项后保存，即可开始使用分析工具
                </p>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
            <div className="flex gap-3">
              <svg className="w-5 h-5 text-red-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            </div>
          </div>
        )}

        <div className="space-y-6">
          {/* LLM 配置 */}
          <div className="card p-6">
            <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
              <svg className="w-5 h-5 text-primary-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              LLM 配置
            </h2>

            <div className="space-y-4">
              {/* API 地址 */}
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                  API 地址
                </label>
                <input
                  type="text"
                  value={config.LLM_API_URL}
                  onChange={(e) => updateConfig('LLM_API_URL', e.target.value)}
                  placeholder="https://api.openai.com/v1 or https://generativelanguage.googleapis.com/v1beta"
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  支持 OpenAI 格式的 API 接口，可使用代理地址
                </p>
              </div>

              {/* API Key */}
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                  API Key <span className="text-red-500">*</span>
                </label>
                <input
                  type="password"
                  value={config.LLM_API_KEY}
                  onChange={(e) => updateConfig('LLM_API_KEY', e.target.value)}
                  placeholder="sk-..."
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>

              {/* 模型选择 */}
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                  模型
                </label>
                <select
                  value={config.LLM_MODEL}
                  onChange={(e) => updateConfig('LLM_MODEL', e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                >
                  {MODEL_OPTIONS.map(option => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* 搜索引擎配置 */}
          <div className="card p-6">
            <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-4 flex items-center gap-2">
              <svg className="w-5 h-5 text-primary-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              搜索引擎配置 (Tavily)
            </h2>

            <div className="space-y-4">
              {/* Tavily API Key */}
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Tavily API Key <span className="text-red-500">*</span>
                </label>
                <input
                  type="password"
                  value={config.TAVILY_API_KEY}
                  onChange={(e) => updateConfig('TAVILY_API_KEY', e.target.value)}
                  placeholder="tvly-..."
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  免费注册获取：
                  <a 
                    href="https://tavily.com" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-primary-600 dark:text-primary-400 hover:underline ml-1"
                  >
                    tavily.com
                  </a>
                  （每月 1000 次免费额度）
                </p>
              </div>
            </div>
          </div>

          {/* 保存按钮 */}
          <div className="flex gap-3">
            <button
              onClick={handleSave}
              disabled={saving}
              className="btn-primary flex-1 flex items-center justify-center gap-2"
            >
              {saving ? (
                <>
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  保存中...
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  保存配置
                </>
              )}
            </button>
            {!isFirstTime && onCancel && (
              <button
                onClick={onCancel}
                className="btn-secondary"
              >
                取消
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
