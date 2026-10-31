import { useEffect, useState } from 'react'
import { api, chooseAnalyst, currentAnalyst, type Analyst } from './api'
import { Button } from './ui'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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
  const [version, setVersion] = useState(0)

  useEffect(() => {
    api.analysts().then(setAnalysts).catch(() => setAnalysts([]))
  }, [])

  const refresh = () => setVersion((v) => v + 1)
  const page = section || 'dashboard'

  return (
    <TooltipProvider>
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
            <DropdownMenu>
              <DropdownMenuTrigger className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-slate-100">
                <Avatar size="sm">
                  <AvatarImage src={avatarUrl(analyst)} alt={analysts.find((a) => a.id === analyst)?.name ?? analyst} />
                  <AvatarFallback>{initials(analysts.find((a) => a.id === analyst)?.name ?? analyst)}</AvatarFallback>
                </Avatar>
                <span className="hidden sm:inline">{analysts.find((a) => a.id === analyst)?.name ?? analyst}</span>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuGroup>
                  <DropdownMenuLabel>Change analyst</DropdownMenuLabel>
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
                {analysts.map((a) => (
                  <DropdownMenuItem
                    key={a.id}
                    onClick={() => {
                      chooseAnalyst(a.id)
                      setAnalyst(a.id)
                      refresh()
                    }}
                  >
                    <Avatar size="sm">
                      <AvatarImage src={avatarUrl(a.id)} alt={a.name} />
                      <AvatarFallback>{initials(a.name)}</AvatarFallback>
                    </Avatar>
                    {a.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
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
