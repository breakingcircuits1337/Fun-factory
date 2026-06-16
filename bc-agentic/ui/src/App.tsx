import { Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import TaskDetail from './pages/TaskDetail'

function NavBar() {
  return (
    <nav className="border-b border-gray-800 px-6 py-3 flex items-center gap-6">
      <a href="/" className="text-green-400 font-bold text-lg tracking-widest">BC-AGENTIC</a>
      <a href="/" className="text-gray-400 hover:text-gray-100 text-sm">Tasks</a>
      <a href="/repos" className="text-gray-400 hover:text-gray-100 text-sm">Repos</a>
    </nav>
  )
}

export default function App() {
  return (
    <div className="min-h-screen">
      <NavBar />
      <main className="max-w-7xl mx-auto px-6 py-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/tasks/:taskId" element={<TaskDetail />} />
        </Routes>
      </main>
    </div>
  )
}
