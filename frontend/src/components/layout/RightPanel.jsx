import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, Terminal, Database, HardDrive } from 'lucide-react'
import { workspaceApi } from '../../api/workspace'
import { Spinner } from '../ui/Primitives'

const TABS = [
  { id: 'files', label: 'Files', icon: FileText },
  { id: 'tools', label: 'Tools', icon: Terminal },
]

export default function RightPanel() {
  const [activeTab, setActiveTab] = useState('files')

  return (
    <div className="right-panel">
      <div className="right-panel-tabs">
        {TABS.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              className={`right-panel-tab${activeTab === tab.id ? ' active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon size={13} style={{ marginRight: 4 }} />
              {tab.label}
            </button>
          )
        })}
      </div>
      <div className="right-panel-content">
        {activeTab === 'files' && <FilesPanel />}
        {activeTab === 'tools' && <ToolsPanel />}
      </div>
    </div>
  )
}

function FilesPanel() {
  const { data: tree, isLoading } = useQuery({
    queryKey: ['workspace', 'tree'],
    queryFn: () => workspaceApi.tree(),
    staleTime: 30_000,
  })

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}>
        <Spinner />
      </div>
    )
  }

  if (!tree || tree.length === 0) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
        <HardDrive size={24} style={{ marginBottom: 8, opacity: 0.5 }} />
        <p>No files in workspace</p>
      </div>
    )
  }

  return (
    <div>
      {tree.map((node) => (
        <FileNode key={node.path} node={node} depth={0} />
      ))}
    </div>
  )
}

function FileNode({ node, depth }) {
  const [expanded, setExpanded] = useState(depth < 1)
  const indent = depth * 12

  if (node.is_dir) {
    return (
      <div>
        <div
          className="file-tree-item"
          style={{ paddingLeft: 8 + indent }}
          onClick={() => setExpanded(!expanded)}
        >
          <span className="file-icon" style={{ color: 'var(--accent-yellow)' }}>
            {expanded ? '▾' : '▸'}
          </span>
          <span className="file-name">{node.name}</span>
        </div>
        {expanded && node.children?.map((child) => (
          <FileNode key={child.path} node={child} depth={depth + 1} />
        ))}
      </div>
    )
  }

  const ext = node.name.split('.').pop()?.toLowerCase()
  const colors = {
    py: '#3572A5', js: '#f1e05a', ts: '#3178c6', jsx: '#61dafb',
    json: '#666', md: '#22c55e', sh: '#89e051', css: '#563d7c',
    html: '#e34c26', sql: '#e38c00',
  }

  return (
    <div className="file-tree-item" style={{ paddingLeft: 8 + indent }}>
      <span className="file-icon" style={{ color: colors[ext] || '#666', fontSize: 9, fontWeight: 700 }}>
        {ext?.toUpperCase().slice(0, 2) || '·'}
      </span>
      <span className="file-name">{node.name}</span>
      {node.size != null && (
        <span className="file-size">{formatBytes(node.size)}</span>
      )}
    </div>
  )
}

function ToolsPanel() {
  const { data: tools, isLoading } = useQuery({
    queryKey: ['tools'],
    queryFn: () => import('../../api/tools').then(m => m.toolsApi.list()),
    staleTime: 30_000,
  })

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}>
        <Spinner />
      </div>
    )
  }

  if (!tools || tools.length === 0) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
        <Terminal size={24} style={{ marginBottom: 8, opacity: 0.5 }} />
        <p>No tools registered</p>
      </div>
    )
  }

  return (
    <div>
      {tools.map((tool) => (
        <div
          key={tool.name}
          style={{
            padding: '10px 8px',
            borderBottom: '1px solid var(--border-secondary)',
            fontSize: 12,
          }}
        >
          <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
            {tool.name}
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: 11, lineHeight: 1.4 }}>
            {tool.description}
          </div>
          <div style={{ marginTop: 4 }}>
            <span className="badge" style={{ fontSize: 10 }}>{tool.category}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}
