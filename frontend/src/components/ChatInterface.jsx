import { useState, useRef, useEffect, useCallback } from "react";
import MessageBubble from "./MessageBubble";
import { useChat } from "../hooks/useChat";
import { useSpeech } from "../hooks/useSpeech";

const SUGGESTIONS = [
  "How do I use list comprehensions in Python?",
  "What are Python decorators and how do they work?",
  "How to handle exceptions in Python?",
  "Explain Python's asyncio and async/await",
  "How do I use pandas DataFrames?",
];

/**
 * ChatInterface — Main conversational Q&A UI with STT mic input.
 */
export default function ChatInterface() {
  const { messages, isLoading, sendMessage, clearHistory } = useChat();
  const [input, setInput] = useState("");
  const [interimText, setInterimText] = useState(""); // live interim transcript
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  // STT — append final result to input, show interim as placeholder overlay
  const { isListening, isSupported, error: speechError, toggleListening } = useSpeech({
    onResult: (transcript) => {
      setInterimText("");
      setInput((prev) => {
        const trimmed = prev.trimEnd();
        return trimmed ? `${trimmed} ${transcript}` : transcript;
      });
      inputRef.current?.focus();
    },
    onInterim: (partial) => {
      setInterimText(partial);
    },
  });

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const q = input.trim();
    if (!q || isLoading) return;
    setInput("");
    setInterimText("");
    sendMessage(q);
  };

  const handleSuggestion = (text) => {
    setInput(text);
    inputRef.current?.focus();
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="chat-container">
      {/* Messages area */}
      <div className="messages-area">
        {isEmpty ? (
          <div className="empty-state">
            <div className="empty-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
                <path d="M8 12h.01M12 12h.01M16 12h.01"/>
              </svg>
            </div>
            <h2 className="empty-title">Python Q&amp;A Assistant</h2>
            <p className="empty-subtitle">
              Powered by Stack Overflow + GPT-4o. Ask by typing or click the mic to speak.
            </p>
            <div className="suggestions">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  className="suggestion-btn"
                  onClick={() => handleSuggestion(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Speech error toast */}
      {speechError && (
        <div className="speech-error">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
          </svg>
          {speechError}
        </div>
      )}

      {/* Input area */}
      <div className="input-area">
        <div className="input-controls">

          {/* Mic button (STT) */}
          {isSupported && (
            <button
              className={`mic-btn ${isListening ? "mic-active" : ""}`}
              onClick={toggleListening}
              title={isListening ? "Stop recording" : "Speak your question"}
              aria-label={isListening ? "Stop recording" : "Start voice input"}
              type="button"
            >
              {isListening ? (
                /* Animated mic-off / stop icon */
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="9" y="9" width="6" height="6" rx="1"/>
                  <path d="M12 1a3 3 0 0 0-3 3v5h6V4a3 3 0 0 0-3-3z" opacity="0.4"/>
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2H3v2a9 9 0 0 0 8 8.94V23h2v-2.06A9 9 0 0 0 21 12v-2h-2z" opacity="0.4"/>
                </svg>
              ) : (
                /* Mic icon */
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2H3v2a9 9 0 0 0 8 8.94V23h2v-2.06A9 9 0 0 0 21 12v-2h-2z"/>
                </svg>
              )}
              {isListening && <span className="mic-pulse" />}
            </button>
          )}

          {/* Text input */}
          <form className="input-form" onSubmit={handleSubmit}>
            <div className="input-wrap">
              <textarea
                ref={inputRef}
                className={`chat-input ${isListening ? "chat-input-listening" : ""}`}
                placeholder={
                  isListening
                    ? interimText
                      ? interimText
                      : "Listening… speak your question"
                    : "Ask a Python question…"
                }
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
                rows={1}
                disabled={isLoading}
              />
            </div>

            <button
              type="submit"
              className={`send-btn ${isLoading ? "send-loading" : ""}`}
              disabled={!input.trim() || isLoading}
              aria-label="Send"
            >
              {isLoading ? (
                <span className="spinner" />
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                </svg>
              )}
            </button>
          </form>

          {/* Clear history */}
          {messages.length > 0 && (
            <button
              className="clear-btn"
              onClick={clearHistory}
              title="Clear chat"
              aria-label="Clear chat history"
              type="button"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6l-1 14H6L5 6"/>
                <path d="M10 11v6M14 11v6"/>
                <path d="M9 6V4h6v2"/>
              </svg>
            </button>
          )}
        </div>

        <p className="input-hint">
          {isListening
            ? "🎙 Listening… speak your question, then it will appear above"
            : isSupported
            ? "Press Enter to send • Shift+Enter for new line • 🎙 mic to speak"
            : "Press Enter to send • Shift+Enter for new line"}
        </p>
      </div>
    </div>
  );
}
