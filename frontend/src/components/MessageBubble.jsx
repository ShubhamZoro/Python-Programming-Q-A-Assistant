import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import SourceCards from "./SourceCards";

/**
 * MessageBubble — Renders a single chat message with markdown + source cards.
 * TTS removed; STT is handled in the input bar instead.
 */
export default function MessageBubble({ message }) {
  if (message.role === "user") {
    return (
      <div className="message-wrap message-user-wrap">
        <div className="message message-user">
          <p>{message.content}</p>
        </div>
      </div>
    );
  }

  // Assistant — loading skeleton
  if (message.loading) {
    return (
      <div className="message-wrap message-assistant-wrap">
        <div className="message message-assistant message-skeleton">
          <div className="skeleton-line" style={{ width: "80%" }} />
          <div className="skeleton-line" style={{ width: "60%" }} />
          <div className="skeleton-line" style={{ width: "70%" }} />
        </div>
      </div>
    );
  }

  // Assistant — error
  if (message.error) {
    return (
      <div className="message-wrap message-assistant-wrap">
        <div className="message message-error">
          <div className="error-icon">⚠</div>
          <p>{message.error}</p>
        </div>
      </div>
    );
  }

  // Assistant — normal answer
  return (
    <div className="message-wrap message-assistant-wrap">
      <div className="message message-assistant">
        {/* Grounded indicator */}
        <div className="message-meta">
          <span className={`grounded-badge ${message.grounded ? "grounded-yes" : "grounded-no"}`}>
            {message.grounded ? (
              <>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                </svg>
                Grounded in sources
              </>
            ) : (
              <>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                </svg>
                Model knowledge
              </>
            )}
          </span>
        </div>

        {/* Markdown content */}
        <div className="markdown-body">
          <ReactMarkdown
            components={{
              code({ node, inline, className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || "");
                return !inline && match ? (
                  <div className="code-block-wrap">
                    <div className="code-lang-badge">{match[1]}</div>
                    <SyntaxHighlighter
                      style={vscDarkPlus}
                      language={match[1]}
                      PreTag="div"
                      customStyle={{
                        margin: 0,
                        borderRadius: "0 0 8px 8px",
                        fontSize: "0.85rem",
                        background: "#0d0d16",
                      }}
                      {...props}
                    >
                      {String(children).replace(/\n$/, "")}
                    </SyntaxHighlighter>
                  </div>
                ) : (
                  <code className="inline-code" {...props}>
                    {children}
                  </code>
                );
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>

        {/* Source Cards */}
        {message.sources && message.sources.length > 0 && (
          <SourceCards sources={message.sources} />
        )}
      </div>
    </div>
  );
}
