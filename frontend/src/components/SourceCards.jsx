import { useState } from "react";

/**
 * SourceCards — Collapsible source attribution cards below each answer.
 * Shows up to 3 sources with relevance score badges and content preview.
 */
export default function SourceCards({ sources }) {
  const [expanded, setExpanded] = useState({});

  if (!sources || sources.length === 0) return null;

  const toggle = (idx) =>
    setExpanded((prev) => ({ ...prev, [idx]: !prev[idx] }));

  const getScoreColor = (score) => {
    if (score >= 0.8) return "score-high";
    if (score >= 0.6) return "score-mid";
    return "score-low";
  };

  const getScoreLabel = (score) => {
    if (score >= 0.8) return "High";
    if (score >= 0.6) return "Medium";
    return "Low";
  };

  // Extract Q and A from content
  const parseContent = (content) => {
    const qMatch = content.match(/Question:\s*(.*?)(?:\nAnswer:|$)/s);
    const aMatch = content.match(/Answer:\s*(.*)/s);
    return {
      question: qMatch?.[1]?.trim().slice(0, 120) || content.slice(0, 120),
      answer: aMatch?.[1]?.trim().slice(0, 200) || "",
    };
  };

  return (
    <div className="source-cards">
      <div className="sources-header">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        <span>Sources ({sources.length})</span>
      </div>
      <div className="source-list">
        {sources.slice(0, 3).map((source, idx) => {
          const parsed = parseContent(source.content || "");
          const isOpen = expanded[idx];
          const scoreVal = typeof source.score === "number" ? source.score : 0;

          return (
            <div key={idx} className="source-card">
              <button
                className="source-card-header"
                onClick={() => toggle(idx)}
                aria-expanded={isOpen}
              >
                <div className="source-card-left">
                  <span className="source-index">#{idx + 1}</span>
                  <span className="source-question">{parsed.question}</span>
                </div>
                <div className="source-card-right">
                  <span className={`score-badge ${getScoreColor(scoreVal)}`}>
                    {getScoreLabel(scoreVal)} {(scoreVal * 100).toFixed(0)}%
                  </span>
                  <svg
                    className={`chevron ${isOpen ? "chevron-open" : ""}`}
                    width="14" height="14" viewBox="0 0 24 24"
                    fill="none" stroke="currentColor" strokeWidth="2"
                  >
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </div>
              </button>
              {isOpen && (
                <div className="source-card-body">
                  {parsed.answer && (
                    <p className="source-answer-preview">{parsed.answer}…</p>
                  )}
                  <div className="source-meta">
                    <span className="source-tag">Stack Overflow</span>
                    <span className="source-tag">Python</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
