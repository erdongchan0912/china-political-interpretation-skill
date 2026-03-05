import { useMemo } from 'react'

// 阶段定义
export interface StageDefinition {
  id: string
  label: string
}

// 组件 Props
interface ProgressTrackerProps {
  stages: StageDefinition[]
  currentStage: string
  status: 'idle' | 'uploading' | 'analyzing' | 'completed' | 'failed'
  message?: string
  elapsedTime?: number  // in milliseconds
}

// 阶段状态
type StageStatus = 'pending' | 'active' | 'completed' | 'failed'

// 格式化时间
function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}秒`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes}分${remainingSeconds}秒`
}

// 阶段名称映射（从后端返回的中文名映射到阶段ID）
const STAGE_NAME_MAP: Record<string, string> = {
  '正在上传文件...': 'upload',
  '准备中': 'material',
  '识别文本': 'material',
  '材料理解': 'material',
  '检索策略生成': 'strategy',
  '横向检索': 'horizontal',
  '纵向检索': 'vertical',
  '深度分析': 'analysis',
  '报告生成': 'report',
  '完成': 'completed',
  '失败': 'failed',
  // 带 LLM 标识的版本（有空格）
  '🤖 LLM 理解材料': 'material',
  '🤖 LLM 生成检索策略': 'strategy',
  '🤖 LLM 深度分析': 'analysis',
  '🤖 LLM 生成 HTML 报告': 'report',
  '🤖 LLM 生成 PDF 报告': 'report',
  // 带 LLM 标识的版本（无空格 - 后端实际发送）
  '🤖 LLM理解材料': 'material',
  '🤖 LLM生成检索策略': 'strategy',
  '🤖 LLM深度分析': 'analysis',
  '🤖 LLM生成HTML报告': 'report',
  '🤖 LLM生成PDF报告': 'report',
  // 其他后端阶段名
  '搜索横向材料': 'horizontal',
  '搜索纵向材料': 'vertical',
  '构建检索矩阵': 'strategy',
}

export function ProgressTracker({ 
  stages, 
  currentStage, 
  status, 
  message, 
  elapsedTime 
}: ProgressTrackerProps) {
  
  // 计算每个阶段的状态
  const stageStatuses = useMemo(() => {
    const currentStageId = STAGE_NAME_MAP[currentStage] || currentStage
    const currentIndex = stages.findIndex(s => s.id === currentStageId)
    
    return stages.map((stage, index) => {
      let stageStatus: StageStatus = 'pending'
      
      if (status === 'completed') {
        stageStatus = 'completed'
      } else if (status === 'failed') {
        if (index < currentIndex) {
          stageStatus = 'completed'
        } else if (index === currentIndex || stage.id === currentStageId) {
          stageStatus = 'failed'
        }
      } else if (status === 'uploading' || status === 'analyzing') {
        if (index < currentIndex) {
          stageStatus = 'completed'
        } else if (index === currentIndex || stage.id === currentStageId) {
          stageStatus = 'active'
        }
      }
      
      return { ...stage, status: stageStatus }
    })
  }, [stages, currentStage, status])

  return (
    <div className="space-y-4">
      {/* 阶段列表 */}
      <div className="space-y-1">
        {stageStatuses.map((stage, index) => (
          <div
            key={stage.id}
            className="progress-step"
            style={{ 
              animationDelay: `${index * 50}ms`,
              opacity: stage.status === 'pending' ? 0.5 : 1 
            }}
          >
            {/* 状态指示器 */}
            <div className={`progress-step-indicator ${stage.status}`}>
              {stage.status === 'completed' ? (
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                </svg>
              ) : stage.status === 'active' ? (
                <div className="w-2 h-2 bg-white rounded-full" />
              ) : stage.status === 'failed' ? (
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
                </svg>
              ) : (
                <span className="text-xs">{index + 1}</span>
              )}
            </div>
            
            {/* 阶段名称 */}
            <span 
              className={`text-sm ${
                stage.status === 'active' ? 'font-medium' : ''
              }`}
              style={{ 
                color: stage.status === 'active' 
                  ? 'var(--tech-color)' 
                  : stage.status === 'completed'
                  ? 'var(--text-primary)'
                  : stage.status === 'failed'
                  ? 'var(--error-color)'
                  : 'var(--text-muted)'
              }}
            >
              {stage.label}
            </span>
          </div>
        ))}
      </div>

      {/* 错误消息 */}
      {message && status === 'failed' && (
        <div 
          className="text-sm p-3 rounded-lg mt-3"
          style={{ 
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            color: 'var(--error-color)'
          }}
        >
          {message}
        </div>
      )}

      {/* 已用时间 */}
      {elapsedTime !== undefined && elapsedTime > 0 && (
        <div 
          className="flex items-center justify-between pt-3 mt-3 text-sm"
          style={{ borderTop: '1px solid var(--border-color)' }}
        >
          <span style={{ color: 'var(--text-muted)' }}>已用时</span>
          <span 
            className="font-mono font-medium"
            style={{ color: 'var(--text-primary)' }}
          >
            {formatDuration(elapsedTime)}
          </span>
        </div>
      )}
    </div>
  )
}

export default ProgressTracker
