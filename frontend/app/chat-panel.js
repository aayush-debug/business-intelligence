"use client";

import { useState, useEffect, useRef } from "react";
import { API_BASE } from "./api";

const SUGGESTIONS = [
  "How is my profit and margin?",
  "Why was 18 Mar a spike?",
  "What items need reordering?",
  "Any stock alerts or expiring batches?",
  "What are my best selling products?",
  "What is the 30-day sales forecast?",
  "Are any business days unclosed?",
  "Are there any profit leaks or discount losses?",
];

export default function ChatPanel({ compact = false }) {
  const [messages, setMessages] = useState([
    {
      sender: "assistant",
      text: "Hello! I am your AI Business Intelligence Assistant. I have direct access to your verified sales, inventory, and profit data. Ask me anything about your business performance, stock alerts, or reorder needs.",
      time: "Just now",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [thinkingStatus, setThinkingStatus] = useState("Consulting sales records…");
  const [lastClosedDate, setLastClosedDate] = useState(null);
  const threadRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/day/status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.last_closed_date) {
          setLastClosedDate(data.last_closed_date);
        }
      })
      .catch(() => {});
  }, []);

  const scrollToBottom = () => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    if (messages.length > 1 || loading) {
      scrollToBottom();
    }
  }, [messages, loading]);

  const sendMessage = async (textToSend) => {
    const query = (textToSend || input).trim();
    if (!query || loading) return;

    const userMsg = {
      sender: "user",
      text: query,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setThinkingStatus("Consulting sales records…");

    // Realistic progressive thinking delays
    const statusTimer1 = setTimeout(() => {
      setThinkingStatus("Analyzing metrics & stock…");
    }, 400);
    const statusTimer2 = setTimeout(() => {
      setThinkingStatus("Formulating answer…");
    }, 850);

    const minThinkingTime = 950 + Math.floor(Math.random() * 300);

    try {
      const fetchPromise = fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: query }),
      });

      const delayPromise = new Promise((resolve) => setTimeout(resolve, minThinkingTime));

      const [res] = await Promise.all([fetchPromise, delayPromise]);

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`);
      }

      const data = await res.json();
      const replyText = data.reply || "I couldn't process that query. Please try asking in a different way.";
      if (data.last_closed_date) {
        setLastClosedDate(data.last_closed_date);
      }

      setMessages((prev) => [
        ...prev,
        {
          sender: "assistant",
          text: replyText,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          lastClosed: data.last_closed_date,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          sender: "assistant",
          text: "Sorry, I encountered an issue connecting to the analytics server. Please ensure the backend is running.",
          isError: true,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      clearTimeout(statusTimer1);
      clearTimeout(statusTimer2);
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage();
  };

  const handleClear = () => {
    setMessages([
      {
        sender: "assistant",
        text: "Conversation cleared. How can I help you analyze your business numbers today?",
        time: "Just now",
      },
    ]);
  };

  return (
    <div className={`chat-panel ${compact ? "compact" : ""}`}>
      <div className="chat-header">
        <div className="chat-header-info">
          <div className="chat-title-row">
            <span className="chat-avatar-ai">🤖</span>
            <h3 className="chat-title">AI Business Intelligence Assistant</h3>
            {lastClosedDate && (
              <span className="chat-status-pill">
                <span className="status-dot"></span> Data up to {lastClosedDate}
              </span>
            )}
          </div>
          <p className="chat-subtitle">
            Answers are calculated directly from your verified sales, inventory batches, and closed books.
          </p>
        </div>
        <button type="button" onClick={handleClear} className="chat-clear-btn" title="Clear chat history">
          Clear
        </button>
      </div>

      <div className="chat-suggestions">
        <span className="chat-suggestions-label">Suggested:</span>
        <div className="chat-chips-scroll">
          {SUGGESTIONS.map((s, idx) => (
            <button
              key={idx}
              type="button"
              className="chat-chip"
              disabled={loading}
              onClick={() => sendMessage(s)}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div ref={threadRef} className="chat-thread">
        {messages.map((m, idx) => (
          <div key={idx} className={`chat-bubble-wrap ${m.sender}`}>
            {m.sender === "assistant" && <div className="chat-bubble-avatar">🤖</div>}
            <div className={`chat-bubble ${m.sender} ${m.isError ? "error" : ""}`}>
              <div className="chat-bubble-content">
                {m.text.split("\n").map((line, i) => (
                  <p key={i} style={{ margin: i === 0 ? 0 : "4px 0 0 0" }}>
                    {line}
                  </p>
                ))}
              </div>
              <span className="chat-bubble-time">{m.time}</span>
            </div>
          </div>
        ))}

        {loading && (
          <div className="chat-bubble-wrap assistant">
            <div className="chat-bubble-avatar">🤖</div>
            <div className="chat-bubble assistant typing">
              <span className="typing-dot"></span>
              <span className="typing-dot"></span>
              <span className="typing-dot"></span>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", marginLeft: "8px", fontStyle: "italic" }}>
                {thinkingStatus}
              </span>
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="chat-input-form">
        <input
          ref={inputRef}
          type="text"
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about your business data (e.g. 'What products are expiring soon?')..."
          disabled={loading}
        />
        <button type="submit" className="chat-send-btn" disabled={loading || !input.trim()}>
          {loading ? "Thinking..." : "Ask AI →"}
        </button>
      </form>
    </div>
  );
}
