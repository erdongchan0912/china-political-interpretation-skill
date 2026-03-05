import { useState, useCallback, useRef } from 'react'

export interface UploadedFile {
  id: string
  name: string
  type: 'url' | 'pdf' | 'image' | 'text'
  size?: number
  file?: File
  url?: string
  content?: string
}

type InputMode = 'url' | 'file' | 'text'

interface FileUploaderProps {
  files: UploadedFile[]
  onFilesChange: (files: UploadedFile[]) => void
  disabled?: boolean
}

export function FileUploader({ files, onFilesChange, disabled }: FileUploaderProps) {
  const [inputMode, setInputMode] = useState<InputMode>('url')
  const [isDragging, setIsDragging] = useState(false)
  const [urlInput, setUrlInput] = useState('')
  const [textInput, setTextInput] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const generateId = () => Math.random().toString(36).substring(2, 10)

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    if (!disabled) {
      setIsDragging(true)
    }
  }, [disabled])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const processFiles = useCallback((fileList: FileList) => {
    const newFiles: UploadedFile[] = []
    
    Array.from(fileList).forEach(file => {
      const ext = file.name.split('.').pop()?.toLowerCase() || ''
      let type: UploadedFile['type'] = 'text'
      
      if (ext === 'pdf') {
        type = 'pdf'
      } else if (['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)) {
        type = 'image'
      }
      
      newFiles.push({
        id: generateId(),
        name: file.name,
        type,
        size: file.size,
        file,
      })
    })
    
    onFilesChange([...files, ...newFiles])
  }, [files, onFilesChange])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    
    if (disabled) return
    
    if (e.dataTransfer.files.length > 0) {
      processFiles(e.dataTransfer.files)
    }
  }, [disabled, processFiles])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(e.target.files)
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }, [processFiles])

  const handleAddUrl = useCallback(() => {
    const url = urlInput.trim()
    if (!url) return
    
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      alert('请输入有效的URL (以 http:// 或 https:// 开头)')
      return
    }
    
    onFilesChange([
      ...files,
      {
        id: generateId(),
        name: url,
        type: 'url',
        url,
      },
    ])
    setUrlInput('')
  }, [urlInput, files, onFilesChange])

  const handleKeyPress = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleAddUrl()
    }
  }, [handleAddUrl])

  const handleAddText = useCallback(() => {
    const text = textInput.trim()
    if (!text) return
    
    if (text.length < 50) {
      alert('请输入更多内容（至少 50 个字符）')
      return
    }
    
    const summary = text.substring(0, 50).replace(/\n/g, ' ') + '...'
    
    onFilesChange([
      ...files,
      {
        id: generateId(),
        name: summary,
        type: 'text',
        content: text,
        size: new Blob([text]).size,
      },
    ])
    setTextInput('')
  }, [textInput, files, onFilesChange])

  const handleRemoveFile = useCallback((id: string) => {
    onFilesChange(files.filter(f => f.id !== id))
  }, [files, onFilesChange])

  const getFileIcon = (type: UploadedFile['type']) => {
    switch (type) {
      case 'url':
        return (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
        )
      case 'pdf':
        return (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
        )
      case 'image':
        return (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        )
      default:
        return (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        )
    }
  }

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const getTabStyle = (isActive: boolean) => ({
    color: isActive ? 'var(--accent-color)' : 'var(--text-muted)',
    borderColor: isActive ? 'var(--accent-color)' : 'transparent',
    opacity: disabled ? 0.5 : 1,
  })

  return (
    <div className="space-y-4">
      {/* Input Mode Tabs */}
      <div className="flex" style={{ borderBottom: '1px solid var(--border-color)' }}>
        <button
          onClick={() => setInputMode('url')}
          disabled={disabled}
          className="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
          style={getTabStyle(inputMode === 'url')}
        >
          网页链接
        </button>
        <button
          onClick={() => setInputMode('file')}
          disabled={disabled}
          className="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
          style={getTabStyle(inputMode === 'file')}
        >
          上传文件
        </button>
        <button
          onClick={() => setInputMode('text')}
          disabled={disabled}
          className="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
          style={getTabStyle(inputMode === 'text')}
        >
          粘贴文本
        </button>
      </div>

      {/* URL Input Mode */}
      {inputMode === 'url' && (
        <div className="space-y-3">
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            输入新闻或政策网页的链接
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="https://..."
              disabled={disabled}
              className="flex-1 px-3 py-2 text-sm rounded-lg transition-colors focus:outline-none focus:ring-2"
              style={{
                backgroundColor: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
              }}
            />
            <button
              onClick={handleAddUrl}
              disabled={disabled || !urlInput.trim()}
              className="btn-secondary px-3 text-sm"
            >
              添加
            </button>
          </div>
        </div>
      )}

      {/* File Upload Mode */}
      {inputMode === 'file' && (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => !disabled && fileInputRef.current?.click()}
          className="relative border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all duration-200"
          style={{
            borderColor: isDragging ? 'var(--accent-color)' : 'var(--border-color)',
            backgroundColor: isDragging ? 'rgba(220, 38, 38, 0.05)' : 'transparent',
            opacity: disabled ? 0.5 : 1,
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg,.webp,.gif,.txt,.md"
            onChange={handleFileSelect}
            disabled={disabled}
            className="hidden"
          />
          
          <div className="flex flex-col items-center gap-2">
            <div className="p-2 rounded-full" style={{ backgroundColor: 'var(--bg-secondary)' }}>
              <svg className="w-6 h-6" style={{ color: 'var(--text-muted)' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                拖拽或点击选择
              </p>
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                PDF / 图片 / 文本
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Text Input Mode */}
      {inputMode === 'text' && (
        <div className="space-y-3">
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            直接粘贴政策文本或新闻内容
          </p>
          <textarea
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="在此粘贴内容..."
            disabled={disabled}
            rows={5}
            className="w-full px-3 py-2 text-sm rounded-lg resize-none focus:outline-none focus:ring-2 transition-colors"
            style={{
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-color)',
              color: 'var(--text-primary)',
            }}
          />
          <div className="flex justify-between items-center">
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {textInput.length > 0 ? `${textInput.length} 字` : '至少 50 字'}
            </span>
            <button
              onClick={handleAddText}
              disabled={disabled || textInput.trim().length < 50}
              className="btn-secondary px-3 text-sm"
            >
              添加
            </button>
          </div>
        </div>
      )}

      {/* File List */}
      {files.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
            已添加 {files.length} 项
          </h3>
          <ul className="space-y-1.5">
            {files.map((file) => (
              <li
                key={file.id}
                className="flex items-center gap-2 p-2 rounded-lg"
                style={{ backgroundColor: 'var(--bg-secondary)' }}
              >
                <span 
                  className="p-1.5 rounded"
                  style={{
                    backgroundColor: file.type === 'url' ? 'rgba(59, 130, 246, 0.15)' :
                                   file.type === 'pdf' ? 'rgba(239, 68, 68, 0.15)' :
                                   file.type === 'image' ? 'rgba(34, 197, 94, 0.15)' :
                                   'var(--border-color)',
                    color: file.type === 'url' ? '#3b82f6' :
                          file.type === 'pdf' ? '#ef4444' :
                          file.type === 'image' ? '#22c55e' :
                          'var(--text-secondary)'
                  }}
                >
                  {getFileIcon(file.type)}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                    {file.name}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {file.type === 'url' ? '链接' : 
                     file.type === 'text' && file.content ? `${file.content.length} 字` :
                     formatFileSize(file.size)}
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    handleRemoveFile(file.id)
                  }}
                  disabled={disabled}
                  className="p-1 rounded transition-colors"
                  style={{ color: 'var(--text-muted)' }}
                  title="移除"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default FileUploader
