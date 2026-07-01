import type { Metadata } from 'next'
import { ChatPanel } from './components/ChatPanel'
import { flags } from '@/lib/feature-flags'

export const metadata: Metadata = { title: 'Paper Assistant' }

export default function ChatPage() {
  if (!flags.SHOW_CHAT_INTERFACE) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="text-gray-500 text-sm">
          Chat interface is not yet enabled. Set{' '}
          <code className="font-mono bg-gray-100 px-1 rounded">NEXT_PUBLIC_SHOW_CHAT=true</code>{' '}
          in <code className="font-mono bg-gray-100 px-1 rounded">web/.env.local</code>.
        </p>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen flex-col bg-gray-50">
      <ChatPanel />
    </main>
  )
}
