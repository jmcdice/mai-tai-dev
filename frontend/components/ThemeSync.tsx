'use client'

import { useEffect, useRef } from 'react'
import { useAuth } from '@/lib/auth'
import { useTheme, type PaletteId } from '@/lib/theme'
import { updateMe } from '@/lib/api'

/**
 * Bridges the (auth-agnostic) ThemeProvider with the signed-in user's
 * server-side settings so theme + palette follow the user across devices.
 *
 * - On first load once the user is known, hydrate theme/palette from
 *   server settings (server wins over the localStorage default).
 * - After hydration, persist any change back to the server via updateMe.
 *
 * Renders nothing.
 */
export function ThemeSync() {
  const { user, token } = useAuth()
  const { theme, setTheme, palette, setPalette } = useTheme()
  const hydrated = useRef(false)

  // Hydrate from server settings once, when the user first becomes available.
  useEffect(() => {
    if (!user || hydrated.current) return
    hydrated.current = true
    const s = user.settings
    if (s?.theme) setTheme(s.theme)
    if (s?.palette) setPalette(s.palette as PaletteId)
  }, [user, setTheme, setPalette])

  // Persist changes back to the server (only after hydration, only if signed in).
  useEffect(() => {
    if (!hydrated.current || !token) return
    updateMe(token, { settings: { theme, palette } }).catch(() => {
      // best-effort; localStorage remains the source of truth for this device
    })
  }, [theme, palette, token])

  return null
}
