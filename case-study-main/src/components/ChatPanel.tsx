"use client";

import { useRef, useEffect } from "react";
import { ChatMessage } from "@/types/chat";
import MessageBubble from "./MessageBubble";
import QuickSuggestions from "./QuickSuggestions";

interface Props {
  messages: ChatMessage[];
  suggestedActions: string[];
  input: string;
  isLoading: boolean;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onSuggestionSelect: (action: string) => void;
}

export default function ChatPanel({
  messages,
  suggestedActions,
  input,
  isLoading,
  onInputChange,
  onSend,
  onSuggestionSelect,
}: Props) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 py-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested actions */}
      {!isLoading && suggestedActions.length > 0 && (
        <QuickSuggestions
          actions={suggestedActions}
          onSelect={onSuggestionSelect}
        />
      )}

      {/* Input */}
      <div className="border-t border-[var(--ps-gray-200)] p-4">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about refrigerator or dishwasher parts..."
            disabled={isLoading}
            className="flex-1 rounded-full border border-[var(--ps-gray-300)] px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--ps-blue)] focus:ring-1 focus:ring-[var(--ps-blue)] disabled:opacity-50 disabled:bg-[var(--ps-gray-50)]"
          />
          <button
            onClick={onSend}
            disabled={isLoading || !input.trim()}
            className="flex-shrink-0 w-10 h-10 rounded-full bg-[var(--ps-blue)] text-white flex items-center justify-center hover:bg-[var(--ps-blue-dark)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
