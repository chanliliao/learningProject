/**
 * SupportChat — conversational UI for querying the support agent about a run.
 *
 * Sends questions to `POST /api/runs/{runId}/support` and displays the agent's
 * answer plus any proposed field-remapping edits.  Each edit proposal has an
 * "Apply" button that POSTs to `POST /api/runs/{runId}/support/apply`, which
 * queues the edit for human review.
 */

import React from 'react'
import { useMutation } from '@tanstack/react-query'
import { askSupport, applyProposedEdit } from '../api'
import type { EditIntent } from '../api'

/** A single message in the chat history. */
type Message = {
  role: 'user' | 'assistant'
  text: string
  /** Proposed field edits attached to assistant messages. */
  proposed_edits?: EditIntent[]
}

/** Props for `SupportChat`. */
type Props = {
  /** ID of the pipeline run being queried. */
  runId: number
}

/**
 * Chat interface for the pipeline support agent.
 *
 * Maintains a local `messages` array that grows as the user asks questions.
 * The agent's response is appended after each successful call.  Proposed edits
 * are rendered inline beneath each assistant message.
 *
 * @param props.runId - The run ID passed to the support API.
 */
export default function SupportChat({ runId }: Props) {
  const [messages, setMessages] = React.useState<Message[]>([])
  const [input, setInput] = React.useState('')

  /**
   * Mutation that calls `POST /api/runs/{runId}/support`.
   * On success, appends both the user question and the assistant reply to `messages`.
   */
  const ask = useMutation({
    mutationFn: (question: string) => askSupport(runId, question),
    onSuccess: (data, question) => {
      setMessages(prev => [
        ...prev,
        { role: 'user', text: question },
        { role: 'assistant', text: data.answer, proposed_edits: data.proposed_edits },
      ])
    },
  })

  /**
   * Mutation that calls `POST /api/runs/{runId}/support/apply`.
   * Queues the edit for review — does not apply it immediately.
   */
  const apply = useMutation({
    mutationFn: (intent: EditIntent) => applyProposedEdit(intent.run_id, intent),
  })

  /** Submit handler — sends the current input as a question if non-empty. */
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const q = input.trim()
    if (!q || ask.isPending) return
    setInput('')
    ask.mutate(q)
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Message history */}
      <div className="space-y-3 max-h-96 overflow-y-auto">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-prose rounded-lg px-4 py-2 text-sm ${
              msg.role === 'user'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-900'
            }`}>
              <p>{msg.text}</p>
              {/* Proposed edit actions rendered below the assistant message */}
              {msg.proposed_edits && msg.proposed_edits.length > 0 && (
                <div className="mt-2 space-y-1 border-t border-gray-200 pt-2">
                  {msg.proposed_edits.map((edit, j) => (
                    <div key={j} className="flex items-center gap-2 text-xs">
                      <span className="font-mono bg-white/50 px-1 rounded">
                        → {edit.new_target_path}
                      </span>
                      <span className="text-gray-600">{edit.reason}</span>
                      <button
                        onClick={() => apply.mutate(edit)}
                        disabled={apply.isPending}
                        className="ml-auto bg-green-600 text-white px-2 py-0.5 rounded text-xs hover:bg-green-700 disabled:opacity-50"
                      >
                        Apply
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {ask.isPending && (
          <div className="text-sm text-gray-400 italic">Thinking...</div>
        )}
      </div>

      {/* Input form */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Ask a question about this run..."
          className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          type="submit"
          disabled={ask.isPending || !input.trim()}
          className="bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  )
}
