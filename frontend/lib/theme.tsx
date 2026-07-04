'use client'

import { createContext, useContext, useEffect, useState } from 'react'

type Theme = 'light' | 'dark' | 'system'
export type PaletteId = 'golden-hour' | 'terminal-tide' | 'jellyseerr'

export interface PaletteMeta {
  id: PaletteId
  label: string
  /** representative dot color for the switcher UI */
  dot: string
}

export const PALETTES: PaletteMeta[] = [
  { id: 'golden-hour', label: 'Golden Hour', dot: '#f17b4d' },
  { id: 'terminal-tide', label: 'Terminal Tide', dot: '#2bd4c0' },
  { id: 'jellyseerr', label: 'Jellyseerr', dot: '#6366f1' },
]

export const DEFAULT_PALETTE: PaletteId = 'golden-hour'

const PALETTE_IDS = PALETTES.map((p) => p.id)
const isPalette = (v: unknown): v is PaletteId =>
  typeof v === 'string' && (PALETTE_IDS as string[]).includes(v)

// Storage keys — must match the inline anti-FOUC script in app/layout.tsx
export const THEME_STORAGE_KEY = 'theme'
export const PALETTE_STORAGE_KEY = 'palette'

interface ThemeContextType {
  theme: Theme
  setTheme: (theme: Theme) => void
  resolvedTheme: 'light' | 'dark'
  palette: PaletteId
  setPalette: (palette: PaletteId) => void
  palettes: PaletteMeta[]
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('system')
  const [palette, setPaletteState] = useState<PaletteId>(DEFAULT_PALETTE)
  const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>('dark')
  const [mounted, setMounted] = useState(false)

  // Initialize from localStorage (set pre-paint by the inline script in layout.tsx)
  useEffect(() => {
    setMounted(true)
    const storedTheme = localStorage.getItem(THEME_STORAGE_KEY) as Theme | null
    if (storedTheme) setThemeState(storedTheme)
    const storedPalette = localStorage.getItem(PALETTE_STORAGE_KEY)
    if (isPalette(storedPalette)) setPaletteState(storedPalette)
  }, [])

  // Apply the .dark class based on mode (+ system preference)
  useEffect(() => {
    if (!mounted) return
    const root = document.documentElement

    const applyMode = (isDark: boolean) => {
      root.classList.toggle('dark', isDark)
      setResolvedTheme(isDark ? 'dark' : 'light')
    }

    if (theme === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
      applyMode(mediaQuery.matches)
      const handler = (e: MediaQueryListEvent) => applyMode(e.matches)
      mediaQuery.addEventListener('change', handler)
      return () => mediaQuery.removeEventListener('change', handler)
    }
    applyMode(theme === 'dark')
  }, [theme, mounted])

  // Apply the data-palette attribute
  useEffect(() => {
    if (!mounted) return
    document.documentElement.setAttribute('data-palette', palette)
  }, [palette, mounted])

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme)
    localStorage.setItem(THEME_STORAGE_KEY, newTheme)
  }

  const setPalette = (newPalette: PaletteId) => {
    setPaletteState(newPalette)
    localStorage.setItem(PALETTE_STORAGE_KEY, newPalette)
  }

  return (
    <ThemeContext.Provider
      value={{ theme, setTheme, resolvedTheme, palette, setPalette, palettes: PALETTES }}
    >
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
