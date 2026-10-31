import { useEffect, useState } from 'react'
import { api, clearSession, currentAnalyst, currentPassword, type Analyst } from './api'
import { Button } from './ui'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { MoonIcon, SunIcon } from 'lucide-react'
import CasePage from './pages/CasePage'
import Cases from './pages/Cases'
import Dashboard from './pages/Dashboard'
import Evaluations from './pages/Evaluations'
import Governance from './pages/Governance'
import Upload from './pages/Upload'
import Login from './pages/Login'

const NAV = [
  ['upload', 'Upload'],
  ['dashboard', 'Dashboard'],
  ['cases', 'Case queue'],
  ['evaluations', 'Evaluations'],
  ['governance', 'Governance'],
]

function avatarUrl(seed: string) {
  return `https://api.dicebear.com/9.x/avataaars/svg?seed=${encodeURIComponent(seed)}`
}

function initials(name: string) {
  return name.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()
}

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
  const [authed, setAuthed] = useState(!!currentPassword())
  const [theme, setTheme] = useState(() => localStorage.getItem('fraudlens-theme') ?? 'light')
  const [version, setVersion] = useState(0)

  useEffect(() => {
    api.analysts().then(setAnalysts).catch(() => setAnalysts([]))
  }, [])

  const refresh = () => setVersion((v) => v + 1)
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try { localStorage.setItem('fraudlens-theme', theme) } catch { /* ignore */ }
  }, [theme])
  const page = section || 'dashboard'

  if (!authed) {
    return (
      <TooltipProvider>
        <Login onLogin={() => { setAnalyst(currentAnalyst()); setAuthed(true); refresh() }} />
      </TooltipProvider>
    )
  }

  return (
    <TooltipProvider>
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <a href="#/dashboard" className="font-semibold">FraudLens AI</a>
          <nav className="flex flex-wrap gap-1">
            {NAV.map(([key, text]) => (
              <a
                key={key}
                href={`#/${key}`}
                className={`rounded-md px-3 py-1.5 text-sm ${page === key ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900' : 'text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'}`}
              >
                {text}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <Avatar size="sm">
              <AvatarImage src={avatarUrl(analyst)} alt={analysts.find((a) => a.id === analyst)?.name ?? analyst} />
              <AvatarFallback>{initials(analysts.find((a) => a.id === analyst)?.name ?? analyst)}</AvatarFallback>
            </Avatar>
            <span className="hidden sm:inline text-sm">{analysts.find((a) => a.id === analyst)?.name ?? analyst}</span>
            <Button onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}>
              {theme === 'dark' ? <SunIcon className="h-4 w-4" /> : <MoonIcon className="h-4 w-4" />}
            </Button>
            <Button onClick={() => { clearSession(); setAuthed(false); refresh() }}>Log out</Button>
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
    </TooltipProvider>
  )
}
