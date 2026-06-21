let invoke: ((cmd: string, args?: Record<string, unknown>) => Promise<unknown>) | null = null
let listen: ((event: string, handler: (payload: unknown) => void) => Promise<() => void>) | null = null

async function initTauri() {
  try {
    const core = await import('@tauri-apps/api/core')
    const eventMod = await import('@tauri-apps/api/event')
    invoke = core.invoke
    listen = eventMod.listen as typeof listen
    return true
  } catch {
    return false
  }
}

const tauriReady = initTauri()

export async function ipcInvoke<T = unknown>(command: string, args?: Record<string, unknown>): Promise<T> {
  await tauriReady
  if (invoke) {
    return invoke(command, args) as Promise<T>
  }
  console.warn(`[IPC] No backend: ${command}`, args)
  return Promise.resolve(null as T)
}

export async function ipcListen(event: string, handler: (payload: unknown) => void): Promise<() => void> {
  await tauriReady
  if (listen) {
    return listen(event, (e: unknown) => {
      const ev = e as { payload: unknown }
      handler(ev.payload)
    })
  }
  console.warn(`[IPC] No backend listener: ${event}`)
  return () => {}
}
