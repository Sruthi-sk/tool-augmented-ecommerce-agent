import { ChatResponse } from "@/types/chat";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

let sessionId: string | null = null;

function getSessionId(): string {
  if (!sessionId) {
    if (typeof window !== "undefined") {
      sessionId = localStorage.getItem("partselect_session_id");
    }
    if (!sessionId) {
      sessionId = crypto.randomUUID();
      if (typeof window !== "undefined") {
        localStorage.setItem("partselect_session_id", sessionId);
      }
    }
  }
  return sessionId;
}

export function resetSession(): void {
  sessionId = null;
  if (typeof window !== "undefined") {
    localStorage.removeItem("partselect_session_id");
  }
}

export async function sendMessage(message: string): Promise<ChatResponse> {
  const response = await fetch(`${BACKEND_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      session_id: getSessionId(),
    }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  const data: ChatResponse = await response.json();

  // Update session ID if server assigned one
  if (data.session_id) {
    sessionId = data.session_id;
    if (typeof window !== "undefined") {
      localStorage.setItem("partselect_session_id", data.session_id);
    }
  }

  return data;
}
