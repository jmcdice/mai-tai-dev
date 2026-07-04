import type { Metadata, Viewport } from 'next'
import {
  Inter,
  Hanken_Grotesk,
  Bricolage_Grotesque,
  Space_Grotesk,
  JetBrains_Mono,
  IBM_Plex_Mono,
} from 'next/font/google'
import { Toaster } from '@/components/ui/toaster'
import { AuthProvider } from '@/lib/auth'
import { NextAuthProvider } from '@/components/Providers'
import { ThemeProvider } from '@/lib/theme'
import { ThemeSync } from '@/components/ThemeSync'
import './globals.css'

// Fonts exposed as CSS variables; globals.css maps them to
// --font-sans / --font-display / --font-mono per palette.
const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' })
const hanken = Hanken_Grotesk({ subsets: ['latin'], variable: '--font-hanken', display: 'swap' })
const bricolage = Bricolage_Grotesque({ subsets: ['latin'], variable: '--font-bricolage', display: 'swap' })
const spaceGrotesk = Space_Grotesk({ subsets: ['latin'], variable: '--font-space', display: 'swap' })
const jetbrains = JetBrains_Mono({ subsets: ['latin'], variable: '--font-jetbrains', display: 'swap' })
const plexMono = IBM_Plex_Mono({ subsets: ['latin'], weight: ['400', '500', '600'], variable: '--font-plex', display: 'swap' })

const fontVars = [inter, hanken, bricolage, spaceGrotesk, jetbrains, plexMono]
  .map((f) => f.variable)
  .join(' ')

export const metadata: Metadata = {
  title: 'Mai-Tai',
  description: 'AI agent collaboration platform',
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={fontVars} suppressHydrationWarning>
      <head>
        {/* Anti-FOUC: apply persisted theme before first paint.
            Keys must match THEME_STORAGE_KEY / PALETTE_STORAGE_KEY in lib/theme.tsx. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('theme')||'system';var p=localStorage.getItem('palette')||'golden-hour';var d=document.documentElement;d.setAttribute('data-palette',p);var m=window.matchMedia('(prefers-color-scheme: dark)').matches;d.classList.toggle('dark',t==='dark'||(t==='system'&&m));}catch(e){}})();`,
          }}
        />
      </head>
      <body className="min-h-screen bg-background text-foreground antialiased font-sans">
        <NextAuthProvider>
          <ThemeProvider>
            <AuthProvider>
              <ThemeSync />
              {children}
              <Toaster />
            </AuthProvider>
          </ThemeProvider>
        </NextAuthProvider>
      </body>
    </html>
  )
}

