'use client'

import { useRef, useEffect } from 'react'
import { useChat } from 'ai/react'
import type { Message, ToolInvocation } from 'ai'
import { ToolResultRenderer } from './tool-results/ToolResultRenderer'

export function ChatPanel() {
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const { messages, input, handleInputChange, handleSubmit, isLoading, error } = useChat({
    api: '/api/chat',
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e as unknown as React.FormEvent<HTMLFormElement>)
    }
  }

  function handleTextareaInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    handleInputChange(e)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  return (
    <div className="flex flex-col h-screen max-w-3xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-200 bg-white">
        <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center text-white text-lg font-bold shadow-sm">
          P
        </div>
        <div>
          <p className="text-sm font-semibold text-gray-900">Paper Assistant</p>
          <p className="text-xs text-gray-400">Powered by Claude + MCP tools</p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-16 text-gray-400 text-sm space-y-2">
            <p className="text-2xl">📄</p>
            <p className="font-medium text-gray-600">Ask me about any ArXiv paper</p>
            <p>Try: <span className="italic">&ldquo;Explain the math in 2301.07984&rdquo;</span></p>
            <p>Or: <span className="italic">&ldquo;What should I read before this paper?&rdquo;</span></p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageRow key={msg.id} message={msg} />
        ))}

        {isLoading && (
          <div className="flex gap-2 items-center text-gray-400 text-sm">
            <TypingDots />
            <span>Thinking…</span>
          </div>
        )}

        {error && (
          <div className="text-red-500 text-sm bg-red-50 px-4 py-2 rounded-lg border border-red-100">
            {error.message}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="px-6 py-4 border-t border-gray-200 bg-white"
      >
        <div className="flex gap-3 items-end">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleTextareaInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask about a paper… (Enter to send, Shift+Enter for newline)"
            rows={1}
            className="flex-1 resize-none rounded-xl border border-gray-200 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-gray-50"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="shrink-0 rounded-xl bg-blue-600 text-white px-5 py-3 text-sm font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  )
}

// ---------------------------------------------------------------------------

interface MessageRowProps {
  message: Message
}

function MessageRow({ message }: MessageRowProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] space-y-2 ${isUser ? 'items-end' : 'items-start'} flex flex-col`}>
        {/* Text content */}
        {typeof message.content === 'string' && message.content && (
          <div
            className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
              isUser
                ? 'bg-blue-600 text-white rounded-br-sm'
                : 'bg-white border border-gray-200 text-gray-800 rounded-bl-sm shadow-sm'
            }`}
          >
            {message.content}
          </div>
        )}

        {/* Tool invocations */}
        {message.toolInvocations?.map((inv: ToolInvocation) => (
          <ToolResultRenderer key={inv.toolCallId} invocation={inv} />
        ))}
      </div>
    </div>
  )
}

function TypingDots() {
  return (
    <div className="flex gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </div>
  )
}
