import { useState } from 'react'
import { api } from '../api'
import { Button, Card, ErrorNote, inputClass } from '../ui'

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await api.login(username, password)
      onLogin()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto mt-20 max-w-sm">
      <Card title="Sign in">
        <div className="space-y-3">
          <input aria-label="Username" className={inputClass} placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
          <input aria-label="Password" type="password" className={inputClass} placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <Button primary disabled={!username || !password || busy} onClick={submit}>Sign in</Button>
          <ErrorNote message={error} />
          <p className="text-xs text-slate-500">Dummy users: analyst-1 / analyst-2, password: password</p>
        </div>
      </Card>
    </div>
  )
}
