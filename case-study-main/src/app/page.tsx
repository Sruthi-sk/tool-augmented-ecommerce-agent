"use client";

import { useState, useCallback } from "react";
import { ChatMessage, DetailData } from "@/types/chat";
import { sendMessage } from "@/lib/api";
import ChatPanel from "@/components/ChatPanel";
import DetailPanel from "@/components/DetailPanel";

const WELCOME_MESSAGE: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content:
    "Hi! I'm the PartSelect Parts Assistant. I can help you find refrigerator and dishwasher parts, check compatibility, get installation guides, and troubleshoot problems. What can I help you with?",
};

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [suggestedActions, setSuggestedActions] = useState<string[]>([]);
  const [detailData, setDetailData] = useState<DetailData | null>(null);
  const [responseType, setResponseType] = useState<string | null>(null);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
    };

    const loadingMsg: ChatMessage = {
      id: `loading-${Date.now()}`,
      role: "assistant",
      content: "",
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setInput("");
    setIsLoading(true);
    setSuggestedActions([]);

    try {
      const response = await sendMessage(text);

      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: response.message,
        detailData: response.detail_data,
        responseType: response.response_type,
        sourceUrl: response.source_url,
        suggestedActions: response.suggested_actions,
      };

      setMessages((prev) =>
        prev.filter((m) => !m.isLoading).concat(assistantMsg)
      );
      setSuggestedActions(response.suggested_actions || []);

      if (response.detail_data) {
        setDetailData(response.detail_data);
        setResponseType(response.response_type);
      }
    } catch (error) {
      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        role: "assistant",
        content:
          "I'm having trouble connecting right now. Please make sure the backend is running and try again.",
      };
      setMessages((prev) =>
        prev.filter((m) => !m.isLoading).concat(errorMsg)
      );
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading]);

  const handleSuggestionSelect = useCallback(
    (action: string) => {
      setInput(action);
    },
    []
  );

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="bg-[var(--ps-blue)] text-white px-6 py-3 flex items-center gap-3 shadow-md flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-white flex items-center justify-center">
            <span className="text-[var(--ps-blue)] font-bold text-sm">PS</span>
          </div>
          <div>
            <h1 className="text-base font-semibold leading-tight">
              PartSelect
            </h1>
            <p className="text-[10px] text-blue-200 leading-tight">
              Parts Assistant
            </p>
          </div>
        </div>
      </header>

      {/* Main content — split panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* Chat panel */}
        <div className="w-1/2 border-r border-[var(--ps-gray-200)] flex flex-col min-w-0">
          <ChatPanel
            messages={messages}
            suggestedActions={suggestedActions}
            input={input}
            isLoading={isLoading}
            onInputChange={setInput}
            onSend={handleSend}
            onSuggestionSelect={handleSuggestionSelect}
          />
        </div>

        {/* Detail panel */}
        <div className="w-1/2 overflow-y-auto custom-scrollbar p-4 bg-[var(--ps-gray-50)] min-w-0">
          <DetailPanel responseType={responseType} data={detailData} />
        </div>
      </div>
    </div>
  );
}
