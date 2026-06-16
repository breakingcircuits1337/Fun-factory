import axios from 'axios'
import { useState } from 'react'

interface Task {
  id: string
  status: string
  pr_url?: string
  goal: string
}

interface Props {
  task: Task
  onApproved: () => void
}

export default function PRPreview({ task, onApproved }: Props) {
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const isAwaitingApproval = task.status === 'awaiting_approval'

  const approve = async (approved: boolean) => {
    setSubmitting(true)
    try {
      await axios.post(`/tasks/${task.id}/approve`, { approved, comment })
      onApproved()
    } finally {
      setSubmitting(false)
    }
  }

  if (task.status === 'complete' && task.pr_url) {
    return (
      <div className="bg-green-900/20 border border-green-800 rounded-lg p-4">
        <p className="text-green-400 font-semibold text-sm mb-2">PR Created</p>
        <a
          href={task.pr_url}
          target="_blank"
          rel="noreferrer"
          className="text-blue-400 hover:underline text-sm break-all"
        >
          {task.pr_url}
        </a>
      </div>
    )
  }

  if (!isAwaitingApproval) {
    return null
  }

  return (
    <div className="bg-purple-900/20 border border-purple-800 rounded-lg p-4 space-y-3">
      <p className="text-purple-300 font-semibold text-sm">Human Approval Required</p>
      <p className="text-gray-400 text-sm">
        All quality gates passed. Review the changes and approve or reject the PR.
      </p>
      <textarea
        className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-300 resize-none focus:outline-none focus:border-purple-600"
        rows={3}
        placeholder="Optional comment..."
        value={comment}
        onChange={(e) => setComment(e.target.value)}
      />
      <div className="flex gap-3">
        <button
          onClick={() => approve(true)}
          disabled={submitting}
          className="px-4 py-2 bg-green-700 hover:bg-green-600 text-white text-sm rounded disabled:opacity-50"
        >
          Approve & Push PR
        </button>
        <button
          onClick={() => approve(false)}
          disabled={submitting}
          className="px-4 py-2 bg-red-900 hover:bg-red-800 text-white text-sm rounded disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  )
}
