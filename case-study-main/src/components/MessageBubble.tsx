"use client";

import { ChatMessage } from "@/types/chat";

interface Props {
  message: ChatMessage;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-[var(--ps-blue)] text-white rounded-br-md"
            : "bg-[var(--ps-gray-100)] text-[var(--ps-gray-900)] rounded-bl-md"
        }`}
      >
        {message.isLoading ? (
          <div className="flex items-center gap-1.5 py-1">
            <div className="w-2 h-2 rounded-full bg-current opacity-40 animate-bounce" style={{ animationDelay: "0ms" }} />
            <div className="w-2 h-2 rounded-full bg-current opacity-40 animate-bounce" style={{ animationDelay: "150ms" }} />
            <div className="w-2 h-2 rounded-full bg-current opacity-40 animate-bounce" style={{ animationDelay: "300ms" }} />
          </div>
        ) : (
          <>
            <p className="text-sm leading-relaxed whitespace-pre-wrap">
              {message.content}
            </p>
            {message.sourceUrl && !isUser && (
              <a
                href={message.sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={`text-xs mt-2 block underline ${
                  isUser ? "text-blue-200" : "text-[var(--ps-blue)]"
                }`}
              >
                Source: PartSelect
              </a>
            )}
          </>
        )}
      </div>
    </div>
  );
}
