import type { Metadata } from 'next'
import { Analytics } from '@vercel/analytics/next'
import './globals.css'
import { AuthProvider } from '../lib/auth'
import StickyLookParam from './components/landing2/StickyLookParam'

export const metadata: Metadata = {
  title: 'Filmo — Your Product Launch AI Agent',
  description:
    'Your product launch AI agent. Paste a URL — Filmo reads your product, plans the cut, prices the job, and ships a finished launch video.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        {/* `?look=` selects the film pipeline and sticks. Mounted here rather
            than on the landing so it works from any entry URL — and so it
            cannot be deleted along with a page. */}
        <StickyLookParam />
        <AuthProvider>{children}</AuthProvider>
        <Analytics />
      </body>
    </html>
  )
}
