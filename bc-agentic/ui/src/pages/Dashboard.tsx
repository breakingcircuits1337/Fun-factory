import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import clsx from 'clsx'

interface Task {
  id: string
  goal: string
  repo_url: string
  status: string
  created_at: string
  pr_url?: string
  model_used?: string
}

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-gray-800 text-gray-400',
  planning: 'bg-blue-900 text-blue-300',
  running: 'bg-yellow-900 text-yellow-300',
  complete: 'bg-green-900 text-green-300',
  failed: 'bg-red-900 text-red-300',
  cancelled: 'bg-gray-800 text-gray-500',
  awaiting_approval: 'bg-purple-900 text-purple-300',
}

const MODELS = ['claude-sonnet', 'gpt-4o', 'local-llm']

export default function Dashboard() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [goal, setGoal] = useState('')
  const [repoUrl, setRepoUrl] = useState('')
  const [model, setModel] = useState('claude-sonnet')

  const { data: tasks = [], isLoading } = useQuery<Task[]>({
    queryKey: ['tasks'],
    queryFn: () => axios.get('/tasks').then((r) => r.data),
    refetchInterval: 5000,
  })

  const createMutation = useMutation({
    mutationFn: () =>
      axios.post('/tasks', { goal, repo_url: repoUrl, model, created_by: 'user' }).then((r) => r.data),
    onSuccess: (task) => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      setGoal('')
      setRepoUrl('')
      navigate(`/tasks/${task.id}`)
    },
  })

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-green-400 mb-1">BC-Agentic</h1>
        <p className="text-gray-500 text-sm">Self-hosted AI coding agent platform</p>
      </div>

      {/* New Task Form */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 space-y-4">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">New Task</h2>
        <textarea
          className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 resize-none focus:outline-none focus:border-green-700"
          rows={3}
          placeholder="Describe what you want to build or fix..."
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
        />
        <input
          className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-green-700"
          placeholder="GitHub repo URL (https://github.com/owner/repo)"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
        />
        <div className="flex items-center gap-4">
          <select
            className="bg-gray-950 border border-gray-700 rounded px-3 py-2 text-sm text-gray-300 focus:outline-none"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            {MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <button
            onClick={() => createMutation.mutate()}
            disabled={!goal || !repoUrl || createMutation.isPending}
            className="px-5 py-2 bg-green-700 hover:bg-green-600 text-white text-sm rounded font-semibold disabled:opacity-40"
          >
            {createMutation.isPending ? 'Creating...' : 'Run Agent'}
          </button>
        </div>
        {createMutation.isError && (
          <p className="text-red-400 text-xs">Failed to create task. Check API.</p>
        )}
      </div>

      {/* Task List */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Recent Tasks</h2>
        {isLoading ? (
          <p className="text-gray-600 text-sm">Loading...</p>
        ) : tasks.length === 0 ? (
          <p className="text-gray-600 text-sm">No tasks yet. Create one above.</p>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => (
              <div
                key={task.id}
                onClick={() => navigate(`/tasks/${task.id}`)}
                className="bg-gray-900 border border-gray-800 hover:border-gray-700 rounded-lg p-4 cursor-pointer flex items-start justify-between gap-4"
              >
                <div className="min-w-0">
                  <p className="text-gray-200 text-sm truncate">{task.goal}</p>
                  <p className="text-gray-600 text-xs mt-1 truncate">{task.repo_url}</p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-gray-600 text-xs">{task.model_used}</span>
                  <span className={clsx('text-xs px-2 py-0.5 rounded-full', STATUS_STYLES[task.status] ?? 'bg-gray-800 text-gray-400')}>
                    {task.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
