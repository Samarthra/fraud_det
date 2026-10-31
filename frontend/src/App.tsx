import { useEffect, useState } from 'react'
import { api, chooseAnalyst, currentAnalyst, type Analyst } from './api'
import { Button } from './ui'
import CasePage from './pages/CasePage'
import Cases from './pages/Cases'
import Dashboard from './pages/Dashboard'
import Evaluations from './pages/Evaluations'
import Governance from './pages/Governance'
import Upload from './pages/Upload'

const NAV = [
  ['upload', 'Upload'],
  ['dashboard', 'Dashboard'],
  ['cases', 'Case queue'],
  ['evaluations', 'Evaluations'],
  ['governance', 'Governance'],
]

function useRoute() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const update = () => setHash(window.location.hash)
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  return hash.replace(/^#\/?/, '').split('/')
}

export default function App() {
  const [section = 'dashboard', id] = useRoute()
  const [analysts, setAnalysts] = useState<Analyst[]>([])
  const [analyst, setAnalyst] = useState(currentAnalyst())
  const [version, setVersion] = useState(0)

  useEffect(() => {
    api.analysts().then(setAnalysts).catch(() => setAnalysts([]))
  }, [])

  const refresh = () => setVersion((v) => v + 1)
  const page = section || 'dashboard'

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <a href="#/dashboard" className="font-semibold">FraudLens AI</a>
          <nav className="flex flex-wrap gap-1">
            {NAV.map(([key, text]) => (
              <a
                key={key}
                href={`#/${key}`}
                className={`rounded-md px-3 py-1.5 text-sm ${page === key ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100'}`}
              >
                {text}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <select
              aria-label="Analyst"
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
              value={analyst}
              onChange={(e) => {
                chooseAnalyst(e.target.value)
                setAnalyst(e.target.value)
                refresh()
              }}
            >
              {analysts.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
            <Button onClick={() => api.reset().then(refresh)}>Reset demo</Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6" key={`${analyst}-${version}`}>
        {page === 'upload' && <Upload />}
        {page === 'dashboard' && <Dashboard />}
        {page === 'cases' && !id && <Cases />}
        {page === 'cases' && id && <CasePage id={id} />}
        {page === 'evaluations' && <Evaluations />}
        {page === 'governance' && <Governance />}
      </main>
    </div>
  )
}
