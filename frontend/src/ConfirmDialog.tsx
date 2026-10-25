import { useEffect, useRef, useState, type ReactNode } from 'react'

/** Modal to confirm a delete. With `typeToConfirm`, the button stays off until that text is typed. */
export function ConfirmDialog({ title, children, action, typeToConfirm, onConfirm, onClose }: {
  title: string; children: ReactNode; action: string; typeToConfirm?: string
  onConfirm: () => Promise<unknown>; onClose: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const closeTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => { ref.current?.showModal(); return () => clearTimeout(closeTimer.current) }, [])

  async function confirm() {
    setErr(''); setBusy(true)
    try { await onConfirm(); ref.current?.close() } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <dialog className="confirm" ref={ref} onClose={() => { closeTimer.current = setTimeout(onClose, 150) }}>{/* unmount after the exit transition */}
      <h2>{title}</h2>
      <p>{children}</p>
      {typeToConfirm && (
        <label>Type {typeToConfirm} to confirm<input value={typed} placeholder={typeToConfirm} autoFocus onChange={(e) => setTyped(e.target.value)} /></label>
      )}
      {err && <p className="err">{err}</p>}
      <div className="row">
        <button className="btn" disabled={busy} onClick={() => ref.current?.close()}>Cancel</button>
        <button className="btn danger-fill" disabled={busy || (!!typeToConfirm && typed !== typeToConfirm)} onClick={confirm}>{busy ? 'Deleting…' : action}</button>
      </div>
    </dialog>
  )
}
