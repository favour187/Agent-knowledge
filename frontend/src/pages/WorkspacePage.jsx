import { useState, useEffect, useCallback, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  Play, Square, FolderOpen, FileText, FolderPlus, Trash2,
  ChevronRight, ChevronDown, Save, Plus, Terminal, Code2,
  RefreshCw, FileCode, Braces, Hash, Wrench,
} from 'lucide-react'
import { workspaceApi } from '../api/workspace'
import { apiErrorMessage } from '../api/client'
import { Spinner, EmptyState, ErrorBanner, Modal, ConfirmButton } from '../components/ui/Primitives'

const LANGUAGES = [
  { value: 'python', label: 'Python', icon: FileCode },
  { value: 'javascript', label: 'JavaScript', icon: Braces },
  { value: 'bash', label: 'Bash', icon: Terminal },
  { value: 'typescript', label: 'TypeScript', icon: Hash },
]

const FILE_ICONS = {
  '.py': { color: '#3572A5', label: 'PY' },
  '.js': { color: '#f1e05a', label: 'JS' },
  '.ts': { color: '#3178c6', label: 'TS' },
  '.jsx': { color: '#61dafb', label: 'JX' },
  '.tsx': { color: '#3178c6', label: 'TX' },
  '.json': { color: '#6b7787', label: '{}' },
  '.md': { color: '#3fc9b0', label: 'MD' },
  '.sh': { color: '#89e051', label: 'SH' },
  '.txt': { color: '#6b7787', label: 'TXT' },
  '.yaml': { color: '#cb171e', label: 'YM' },
  '.yml': { color: '#cb171e', label: 'YM' },
  '.html': { color: '#e34c26', label: 'HT' },
  '.css': { color: '#563d7c', label: 'CS' },
  '.sql': { color: '#e38c00', label: 'SQ' },
}

function getFileIcon(name) {
  const ext = '.' + name.split('.').pop()?.toLowerCase()
  return FILE_ICONS[ext] || { color: '#6b7787', label: '·' }
}

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

export default function WorkspacePage() {
  const qc = useQueryClient()
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileContent, setFileContent] = useState('')
  const [isDirty, setIsDirty] = useState(false)
  const [language, setLanguage] = useState('python')
  const [consoleOutput, setConsoleOutput] = useState([])
  const [createOpen, setCreateOpen] = useState(false)
  const [newItemType, setNewItemType] = useState('file')
  const consoleRef = useRef(null)
  const editorRef = useRef(null)

  // File tree
  const { data: tree, isLoading: treeLoading, error: treeError, refetch: refetchTree } = useQuery({
    queryKey: ['workspace', 'tree'],
    queryFn: () => workspaceApi.tree(),
  })

  // Stats
  const { data: stats } = useQuery({
    queryKey: ['workspace', 'stats'],
    queryFn: workspaceApi.stats,
    staleTime: 30_000,
  })

  // Read file
  const readFileMutation = useMutation({
    mutationFn: (path) => workspaceApi.readFile(path),
    onSuccess: (data, path) => {
      setSelectedFile(path)
      setFileContent(data.content)
      setIsDirty(false)
      // Auto-detect language
      const ext = path.split('.').pop()?.toLowerCase()
      const langMap = { py: 'python', js: 'javascript', ts: 'typescript', sh: 'bash' }
      if (langMap[ext]) setLanguage(langMap[ext])
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  // Save file
  const saveMutation = useMutation({
    mutationFn: () => workspaceApi.writeFile(selectedFile, fileContent),
    onSuccess: () => {
      setIsDirty(false)
      toast.success('File saved')
      qc.invalidateQueries({ queryKey: ['workspace', 'tree'] })
      qc.invalidateQueries({ queryKey: ['workspace', 'stats'] })
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  // Execute code
  const executeMutation = useMutation({
    mutationFn: () => workspaceApi.execute(fileContent, language),
    onSuccess: (result) => {
      setConsoleOutput((prev) => [
        ...prev,
        {
          id: Date.now(),
          type: 'execution',
          language,
          success: result.success,
          output: result.output,
          error: result.error,
          exitCode: result.exit_code,
          time: result.execution_time,
          timestamp: new Date().toLocaleTimeString(),
        },
      ])
      if (result.success) toast.success(`Completed in ${result.execution_time.toFixed(2)}s`)
    },
    onError: (e) => {
      setConsoleOutput((prev) => [
        ...prev,
        {
          id: Date.now(),
          type: 'error',
          output: apiErrorMessage(e),
          timestamp: new Date().toLocaleTimeString(),
        },
      ])
      toast.error(apiErrorMessage(e))
    },
  })

  // Delete file
  const deleteMutation = useMutation({
    mutationFn: (path) => workspaceApi.deleteFile(path),
    onSuccess: (_, path) => {
      toast.success('Deleted')
      if (selectedFile === path) {
        setSelectedFile(null)
        setFileContent('')
      }
      qc.invalidateQueries({ queryKey: ['workspace', 'tree'] })
      qc.invalidateQueries({ queryKey: ['workspace', 'stats'] })
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  // Create file/dir
  const createMutation = useMutation({
    mutationFn: ({ path, type, content }) =>
      type === 'dir'
        ? workspaceApi.createDir(path)
        : workspaceApi.writeFile(path, content || ''),
    onSuccess: () => {
      toast.success('Created')
      qc.invalidateQueries({ queryKey: ['workspace', 'tree'] })
      setCreateOpen(false)
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  // Auto-scroll console
  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight
    }
  }, [consoleOutput])

  // Keyboard shortcuts
  useEffect(() => {
    function handleKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        if (selectedFile && isDirty) saveMutation.mutate()
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        if (selectedFile && fileContent) executeMutation.mutate()
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [selectedFile, isDirty, fileContent, saveMutation, executeMutation])

  const handleRun = useCallback(() => {
    if (!fileContent.trim()) {
      toast.error('No code to run')
      return
    }
    setConsoleOutput((prev) => [
      ...prev,
      {
        id: Date.now(),
        type: 'info',
        output: `▶ Running ${language}…`,
        timestamp: new Date().toLocaleTimeString(),
      },
    ])
    executeMutation.mutate()
  }, [fileContent, language, executeMutation])

  const handleClearConsole = useCallback(() => setConsoleOutput([]), [])

  return (
    <div className="page" style={{ maxWidth: '100%', padding: 0 }}>
      {/* Workspace Toolbar */}
      <div className="ws-toolbar">
        <div className="ws-toolbar-left">
          <div className="ws-toolbar-brand">
            <Wrench size={14} style={{ color: 'var(--amber)' }} />
            <span>Workspace</span>
          </div>
          <div className="ws-toolbar-divider" />
          <div className="ws-toolbar-lang">
            {LANGUAGES.map((lang) => {
              const Icon = lang.icon
              return (
                <button
                  key={lang.value}
                  className={`ws-lang-btn${language === lang.value ? ' active' : ''}`}
                  onClick={() => setLanguage(lang.value)}
                  title={lang.label}
                >
                  <Icon size={13} />
                  {lang.label}
                </button>
              )
            })}
          </div>
        </div>

        <div className="ws-toolbar-right">
          {selectedFile && (
            <span className="ws-toolbar-file mono">
              {selectedFile}
              {isDirty && <span style={{ color: 'var(--amber)', marginLeft: 4 }}>●</span>}
            </span>
          )}
          <button
            className="btn btn-sm"
            onClick={() => { if (selectedFile && isDirty) saveMutation.mutate() }}
            disabled={!selectedFile || !isDirty}
            title="Save (⌘S)"
          >
            <Save size={13} /> Save
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleRun}
            disabled={executeMutation.isPending || !selectedFile}
            title="Run (⌘Enter)"
          >
            {executeMutation.isPending ? <Spinner /> : <Play size={13} />}
            {executeMutation.isPending ? 'Running…' : 'Run'}
          </button>
        </div>
      </div>

      <div className="ws-layout">
        {/* File Tree Panel */}
        <div className="ws-sidebar">
          <div className="ws-sidebar-header">
            <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)' }}>
              Files
            </span>
            <div className="flex-row gap-sm">
              <button className="btn-icon" style={{ width: 24, height: 24 }} onClick={() => { setNewItemType('file'); setCreateOpen(true) }} title="New file">
                <Plus size={12} />
              </button>
              <button className="btn-icon" style={{ width: 24, height: 24 }} onClick={() => { setNewItemType('dir'); setCreateOpen(true) }} title="New folder">
                <FolderPlus size={12} />
              </button>
              <button className="btn-icon" style={{ width: 24, height: 24 }} onClick={() => refetchTree()} title="Refresh">
                <RefreshCw size={12} />
              </button>
            </div>
          </div>

          <div className="ws-tree">
            {treeLoading && (
              <div style={{ padding: 20, textAlign: 'center' }}>
                <Spinner />
              </div>
            )}
            {treeError && <ErrorBanner message={apiErrorMessage(treeError)} />}
            {tree && tree.length === 0 && (
              <div className="empty-state" style={{ padding: '24px 12px' }}>
                <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  Workspace is empty. Create a file to get started.
                </p>
              </div>
            )}
            {tree && tree.map((node) => (
              <TreeNode
                key={node.path}
                node={node}
                depth={0}
                selectedFile={selectedFile}
                onFileClick={(path) => readFileMutation.mutate(path)}
                onDelete={(path) => deleteMutation.mutate(path)}
              />
            ))}
          </div>

          {/* Stats footer */}
          {stats && (
            <div className="ws-stats">
              <span>{stats.total_files} files</span>
              <span>·</span>
              <span>{formatBytes(stats.total_size)}</span>
            </div>
          )}
        </div>

        {/* Editor + Console */}
        <div className="ws-main">
          {/* Editor */}
          <div className="ws-editor-wrap">
            {selectedFile ? (
              <textarea
                ref={editorRef}
                className="ws-editor"
                value={fileContent}
                onChange={(e) => {
                  setFileContent(e.target.value)
                  setIsDirty(true)
                }}
                spellCheck={false}
                placeholder="Start typing…"
              />
            ) : (
              <div className="ws-editor-empty">
                <EmptyState
                  title="No file open"
                  hint="Select a file from the tree, or create a new one to start editing."
                  icon={FileText}
                />
              </div>
            )}
          </div>

          {/* Console */}
          <div className="ws-console">
            <div className="ws-console-header">
              <div className="flex-row gap-sm">
                <Terminal size={13} style={{ color: 'var(--teal)' }} />
                <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)' }}>
                  Console
                </span>
                {executeMutation.isPending && <Spinner />}
              </div>
              <button className="btn btn-ghost btn-sm" onClick={handleClearConsole} style={{ padding: '2px 8px' }}>
                Clear
              </button>
            </div>
            <div className="ws-console-output" ref={consoleRef}>
              {consoleOutput.length === 0 && (
                <div className="ws-console-empty">
                  <span className="text-muted">Run code to see output here. <code className="mono">⌘ Enter</code></span>
                </div>
              )}
              {consoleOutput.map((entry) => (
                <ConsoleEntry key={entry.id} entry={entry} />
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Create file/dir modal */}
      {createOpen && (
        <CreateItemModal
          type={newItemType}
          onClose={() => setCreateOpen(false)}
          onCreate={(path, content) => createMutation.mutate({ path, type: newItemType, content })}
        />
      )}
    </div>
  )
}

/* ---------- File Tree Node ---------- */

function TreeNode({ node, depth, selectedFile, onFileClick, onDelete }) {
  const [expanded, setExpanded] = useState(depth < 2)
  const indent = depth * 14

  if (node.is_dir) {
    return (
      <div>
        <div
          className={`ws-tree-item${selectedFile === node.path ? '' : ''}`}
          style={{ paddingLeft: 8 + indent }}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          <FolderOpen size={14} style={{ color: 'var(--amber)', opacity: 0.7 }} />
          <span className="ws-tree-name">{node.name}</span>
        </div>
        {expanded && node.children?.map((child) => (
          <TreeNode
            key={child.path}
            node={child}
            depth={depth + 1}
            selectedFile={selectedFile}
            onFileClick={onFileClick}
            onDelete={onDelete}
          />
        ))}
      </div>
    )
  }

  const icon = getFileIcon(node.name)

  return (
    <div
      className={`ws-tree-item ws-tree-file${selectedFile === node.path ? ' active' : ''}`}
      style={{ paddingLeft: 8 + indent }}
      onClick={() => onFileClick(node.path)}
    >
      <span className="ws-file-icon" style={{ color: icon.color, fontSize: 9, fontWeight: 700, width: 18, textAlign: 'center' }}>
        {icon.label}
      </span>
      <span className="ws-tree-name">{node.name}</span>
      {node.size != null && (
        <span className="ws-tree-size">{formatBytes(node.size)}</span>
      )}
    </div>
  )
}

/* ---------- Console Entry ---------- */

function ConsoleEntry({ entry }) {
  if (entry.type === 'info') {
    return (
      <div className="ws-console-line ws-console-info">
        <span className="ws-console-time">{entry.timestamp}</span>
        <span>{entry.output}</span>
      </div>
    )
  }

  if (entry.type === 'error') {
    return (
      <div className="ws-console-line ws-console-error">
        <span className="ws-console-time">{entry.timestamp}</span>
        <span>Error: {entry.output}</span>
      </div>
    )
  }

  return (
    <div className="ws-console-block">
      <div className={`ws-console-line ${entry.success ? 'ws-console-success' : 'ws-console-error'}`}>
        <span className="ws-console-time">{entry.timestamp}</span>
        <span>
          {entry.success ? '✓' : '✗'} {entry.language} · exit {entry.exitCode} · {entry.time?.toFixed(2)}s
        </span>
      </div>
      {entry.output && (
        <pre className="ws-console-pre">{entry.output}</pre>
      )}
      {entry.error && (
        <pre className="ws-console-pre ws-console-pre-error">{entry.error}</pre>
      )}
    </div>
  )
}

/* ---------- Create Item Modal ---------- */

function CreateItemModal({ type, onClose, onCreate }) {
  const [path, setPath] = useState('')
  const [content, setContent] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    if (!path.trim()) return
    onCreate(path.trim(), type === 'file' ? content : undefined)
  }

  return (
    <Modal title={type === 'dir' ? 'New folder' : 'New file'} onClose={onClose}>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label>Path (relative to workspace root)</label>
          <input
            className="input mono"
            required
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder={type === 'dir' ? 'src/components' : 'src/main.py'}
            autoFocus
          />
        </div>
        {type === 'file' && (
          <div className="field">
            <label>Initial content (optional)</label>
            <textarea
              className="textarea"
              rows={6}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="# Start coding…"
            />
          </div>
        )}
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }}>
          {type === 'dir' ? 'Create folder' : 'Create file'}
        </button>
      </form>
    </Modal>
  )
}
