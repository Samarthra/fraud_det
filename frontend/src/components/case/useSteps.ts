import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type Investigation, type Step } from '../../api'

const REVEAL_MS = 700
const POLL_MS = 500

export function useSteps(investigationId: string | null, tick: number) {
  const [queue, setQueue] = useState<Step[]>([])
  const [shown, setShown] = useState(0)
  const [investigation, setInvestigation] = useState<Investigation | null>(null)
  const [pollFailed, setPollFailed] = useState(false)
  const after = useRef(0)
  const started = useRef<string | null>(null)

  useEffect(() => {
    if (!investigationId) return
    if (started.current !== investigationId) {
      started.current = investigationId
      after.current = 0
      setQueue([])
      setShown(0)
    }
    let stop = false
    async function poll() {
      while (!stop) {
        try {
          const [steps, current] = await Promise.all([
            api.steps(investigationId!, after.current),
            api.investigation(investigationId!),
          ])
          if (stop) return
          if (steps.length) {
            after.current = steps[steps.length - 1].seq
            setQueue((q) => [...q, ...steps])
          }
          setInvestigation(current)
          setPollFailed(false)
          const answering = current.follow_ups.some((f) => f.answer === null)
          if (current.status === 'complete' && !answering) return
        } catch {
          if (stop) return
          setPollFailed(true) // keep trying, so one failure can't freeze the page
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_MS))
      }
    }
    poll()
    return () => {
      stop = true
    }
  }, [investigationId, tick])

  useEffect(() => {
    if (shown >= queue.length) return
    const timer = setTimeout(() => setShown((n) => n + 1), REVEAL_MS)
    return () => clearTimeout(timer)
  }, [shown, queue.length])

  const refresh = useCallback(() => {
    if (investigationId) api.investigation(investigationId).then(setInvestigation)
  }, [investigationId])

  const finished = investigation?.status === 'complete' && shown >= queue.length
  return { steps: queue.slice(0, shown), investigation, finished, refresh, pollFailed }
}
