import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import TaskGraph from '../components/TaskGraph'
import AgentStream from '../components/AgentStream'
import PRPreview from '../components/PRPreview'

interface Task {
  id: string
  goal: string
  repo_url: string
  status: string
  created_at: string
  completed_at?: string
  pr_url?: string
  model_used?: string
  token_usage: number
  error?: string
}

interface TaskNode {
  id: string
  description: string
  status: string
  agent_type: string
  depends_on: string[]
  output?: string
}

export default function TaskDetail() {
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: task, isLoading } = useQuery<Task>({
    queryKey: ['task', taskId],
    queryFn: () => axios.get(`/tasks/${taskId}`).then((r) => r.data),
    refetchInterval: (data) =>
      data && ['complete', 'failed', 'cancelled'].includes(data.status) ? false : 3000,
    enabled: !!taskId,
  })

  const { data: nodes = [] } = useQuery<TaskNode[]>({
    queryKey: ['task-nodes', taskId],
    queryFn: () => axios.get(`/tasks/${taskId}/nodes`).then((r) => r.data),
    refetchInterval: 3000,
    enabled: !!taskId,
  })

  if (isLoading) return <p className="text-gray-600 text-sm">Loading task...</p>
  if (!task) return <p className="text-red-400 text-sm">Task not found</p>

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <button onClick={() => navigate('/')} className="text-gray-500 hover:text-gray-300 text-xs mb-2">← Back</button>
          <h1 className="text-lg font-semibold text-gray-100">{task.goal}</h1>
          <p className="text-gray-600 text-xs mt-1">{task.repo_url}</p>
        </div>
        <div className="text-right shrink-0">
          <span className="text-xs text-gray-500">{task.model_used}</span>
          <br />
          <span className="text-xs text-gray-600">{task.token_usage.toLocaleString()} tokens</span>
        </div>
      </div>

      {task.error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 text-red-300 text-sm">
          <strong>Error:</strong> {task.error}
        </div>
      )}

      <TaskGraph nodes={nodes} />

      <AgentStream taskId={task.id} />

      <PRPreview task={task} onApproved={() => qc.invalidateQueries({ queryKey: ['task', taskId] })} />

      {nodes.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-gray-400">Task Nodes</h3>
          {nodes.map((node) => (
            <div key={node.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-gray-300">{node.description}</span>
                <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">{node.agent_type}</span>
              </div>
              {node.output && (
                <pre className="text-xs text-gray-500 bg-gray-950 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                  {node.output}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
