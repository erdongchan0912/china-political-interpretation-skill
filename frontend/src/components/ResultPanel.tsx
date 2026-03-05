export interface AnalysisResult {
  task_id: string
  success: boolean
  outputs?: {
    html?: { path: string; url: string; exists: boolean }
    pdf?: { path: string; url: string; exists: boolean }
    analysis_json?: { path: string; url: string; exists: boolean }
    analysis_markdown?: { path: string; url: string; exists: boolean }
    query_matrix?: { path: string; url: string; exists: boolean }
  }
  download_urls?: {
    html?: string
    pdf?: string
  }
  error?: string
  // 可选的摘要数据（如果后端提供）
  summary?: {
    title?: string
    executive_summary?: string
    key_findings?: string[]
    token_usage?: number
    reference_count?: number
  }
}

type ResultStatus = 'idle' | 'uploading' | 'analyzing' | 'completed' | 'failed'

interface ResultPanelProps {
  result: AnalysisResult | null
  baseUrl?: string
  duration?: number | null  // in milliseconds
  status: ResultStatus
  message?: string
  reportTitle?: string
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}秒`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes}分${remainingSeconds}秒`
}

export function ResultPanel({ result, baseUrl = '', duration, status, message, reportTitle }: ResultPanelProps) {
  // 失败状态显示错误信息
  if (status === 'failed') {
    const errorMsg = result?.error || message || '未知错误'

    const getErrorSuggestion = (errorText: string) => {
      const msg = errorText.toLowerCase()
      if (msg.includes('api key') || msg.includes('unauthorized') || msg.includes('invalid_argument')) {
        return '请检查 .env 文件中的 LLM_API_KEY 配置是否正确'
      } else if (msg.includes('network') || msg.includes('fetch')) {
        return '请检查网络连接，确保可以访问 Gemini API'
      } else if (msg.includes('timeout')) {
        return '分析超时，可能是文档过长，请尝试缩短内容'
      } else if (msg.includes('rate limit')) {
        return 'API 调用频率超限，请稍后重试'
      } else if (msg.includes('content extraction') || msg.includes('fetch url')) {
        return '无法获取网页内容，请尝试粘贴文本方式输入'
      }
      return '请稍后重试，如问题持续请检查控制台日志'
    }

    return (
      <div className="card p-6" style={{
        borderColor: 'rgba(239, 68, 68, 0.3)',
        backgroundColor: 'rgba(239, 68, 68, 0.05)'
      }}>
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-xl shrink-0" style={{ backgroundColor: 'rgba(239, 68, 68, 0.15)' }}>
            <svg className="w-6 h-6 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-red-400 mb-1">分析失败</h3>
            <p className="text-sm text-red-300/80 break-words">{errorMsg}</p>
            <p className="text-xs mt-3" style={{ color: 'var(--text-muted)' }}>
              💡 {getErrorSuggestion(errorMsg)}
            </p>
          </div>
        </div>
      </div>
    )
  }

  // 未完成或无结果
  if (!result || status !== 'completed') return null

  const { success, outputs, download_urls, summary } = result

  // 后端返回成功但实际失败的情况
  if (!success) {
    return (
      <div className="card p-6" style={{
        borderColor: 'rgba(239, 68, 68, 0.3)',
        backgroundColor: 'rgba(239, 68, 68, 0.05)'
      }}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg" style={{ backgroundColor: 'rgba(239, 68, 68, 0.15)' }}>
            <svg className="w-5 h-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <div>
            <h3 className="font-semibold text-red-400">处理失败</h3>
            <p className="text-sm text-red-300/70">{result.error || '报告生成时出现问题'}</p>
          </div>
        </div>
      </div>
    )
  }

  // 成功状态 - 摘要面板模式
  return (
    <div className="card p-6 space-y-6">
      {/* 标题区域 */}
      <div className="border-b pb-4" style={{ borderColor: 'var(--border-color)' }}>
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg shrink-0" style={{ backgroundColor: 'rgba(0, 212, 170, 0.15)' }}>
            <svg className="w-5 h-5 text-tech-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
              {summary?.title || '政策解读报告'}
            </h2>
            <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
              分析完成 · {new Date().toLocaleDateString('zh-CN')}
            </p>
          </div>
        </div>
      </div>

      {/* 执行摘要 */}
      {summary?.executive_summary && (
        <div>
          <h3 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>
            执行摘要
          </h3>
          <p className="text-sm leading-relaxed" style={{ color: 'var(--text-primary)' }}>
            {summary.executive_summary}
          </p>
        </div>
      )}

      {/* 核心结论 */}
      {summary?.key_findings && summary.key_findings.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>
            核心结论
          </h3>
          <ul className="space-y-2">
            {summary.key_findings.slice(0, 3).map((finding, index) => (
              <li key={index} className="flex items-start gap-2">
                <span className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium shrink-0 mt-0.5"
                  style={{ backgroundColor: 'rgba(220, 38, 38, 0.15)', color: 'var(--accent-color)' }}>
                  {index + 1}
                </span>
                <span className="text-sm" style={{ color: 'var(--text-primary)' }}>{finding}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 统计卡片 */}
      <div className="grid grid-cols-3 gap-3">
        {/* 用时 */}
        <div className="p-3 rounded-lg text-center" style={{ backgroundColor: 'var(--bg-secondary)' }}>
          <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>分析用时</div>
          <div className="text-lg font-bold" style={{ color: 'var(--tech-color)' }}>
            {duration ? formatDuration(duration) : 'N/A'}
          </div>
        </div>
        {/* 参考文献 */}
        <div className="p-3 rounded-lg text-center" style={{ backgroundColor: 'var(--bg-secondary)' }}>
          <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>参考文献</div>
          <div className="text-lg font-bold" style={{ color: 'var(--accent-color)' }}>
            {summary?.reference_count ?? 'N/A'}
          </div>
        </div>
        {/* Token */}
        <div className="p-3 rounded-lg text-center" style={{ backgroundColor: 'var(--bg-secondary)' }}>
          <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Token</div>
          <div className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
            {summary?.token_usage ? `${(summary.token_usage / 1000).toFixed(1)}K` : 'N/A'}
          </div>
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex flex-col gap-3 pt-2">
        {/* 查看完整报告 */}
        {outputs?.html?.exists && (
          <a
            href={baseUrl + outputs.html.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary flex items-center justify-center gap-2 w-full"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
            查看完整报告
          </a>
        )}

        {/* 下载按钮组 */}
        <div className="flex gap-2">
          {download_urls?.html && (
            <a
              href={baseUrl + download_urls.html}
              download={`${reportTitle || summary?.title || '政策解读报告'}.html`}
              className="btn-secondary flex-1 flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              HTML
            </a>
          )}
          {outputs?.pdf?.exists && download_urls?.pdf && (
            <a
              href={baseUrl + download_urls.pdf}
              download={`${reportTitle || summary?.title || '政策解读报告'}.pdf`}
              className="btn-secondary flex-1 flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              PDF
            </a>
          )}
        </div>

        {/* 其他资源链接 */}
        {(outputs?.analysis_json || outputs?.analysis_markdown || outputs?.query_matrix) && (
          <div className="flex gap-2 text-xs">
            {outputs?.analysis_json?.exists && (
              <a
                href={baseUrl + outputs.analysis_json.url}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-1.5 rounded transition-colors"
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  color: 'var(--text-secondary)'
                }}
              >
                分析JSON
              </a>
            )}
            {outputs?.analysis_markdown?.exists && (
              <a
                href={baseUrl + outputs.analysis_markdown.url}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-1.5 rounded transition-colors"
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  color: 'var(--text-secondary)'
                }}
              >
                分析Markdown
              </a>
            )}
            {outputs?.query_matrix?.exists && (
              <a
                href={baseUrl + outputs.query_matrix.url}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-1.5 rounded transition-colors"
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  color: 'var(--text-secondary)'
                }}
              >
                检索矩阵
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default ResultPanel
