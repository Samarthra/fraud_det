import type { ReactNode } from 'react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export function Card({ title, children, action, tooltip }: { title?: string; children: ReactNode; action?: ReactNode; tooltip?: string }) {
  const card = (
    <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  )
  if (!tooltip) return card
  return (
    <Tooltip>
      <TooltipTrigger render={card} />
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  )
}

export function Stat({ label, value, tooltip }: { label: string; value: ReactNode; tooltip?: string }) {
  const card = (
    <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  )
  if (!tooltip) return card
  return (
    <Tooltip>
      <TooltipTrigger render={card} />
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  )
}

const RISK: Record<string, string> = {
  high: 'bg-red-100 text-red-800',
  medium: 'bg-amber-100 text-amber-800',
  low: 'bg-slate-100 text-slate-700',
}

export function Risk({ level }: { level: string }) {
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${RISK[level]}`}>{level}</span>
}

export function Badge({ children, tone = 'slate' }: { children: ReactNode; tone?: 'slate' | 'green' | 'red' | 'amber' | 'blue' }) {
  const tones = {
    slate: 'bg-slate-100 text-slate-700',
    green: 'bg-emerald-100 text-emerald-800',
    red: 'bg-red-100 text-red-800',
    amber: 'bg-amber-100 text-amber-800',
    blue: 'bg-blue-100 text-blue-800',
  }
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>
}

export function Button({
  children,
  onClick,
  disabled,
  primary,
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  primary?: boolean
}) {
  const look = primary
    ? 'bg-blue-700 text-white hover:bg-blue-800 dark:bg-blue-600'
    : 'border border-slate-300 bg-white text-slate-800 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800'
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${look}`}
    >
      {children}
    </button>
  )
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null
  return <p className="rounded-md bg-red-50 p-3 text-sm text-red-800">{message}</p>
}

export function label(value: string) {
  const text = value.replaceAll('_', ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function when(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export const inputClass = 'rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100'
