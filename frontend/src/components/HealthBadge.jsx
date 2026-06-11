import { useEffect, useState } from "react";
import { api } from "../lib/api";

/**
 * HealthBadge — Shows live API health status in the header.
 * Polls GET /health on mount and every 30 seconds.
 */
export default function HealthBadge() {
  const [status, setStatus] = useState("checking"); // "ok" | "error" | "checking"
  const [info, setInfo] = useState(null);

  useEffect(() => {
    const check = async () => {
      try {
        const data = await api.health();
        setStatus("ok");
        setInfo(data);
      } catch {
        setStatus("error");
        setInfo(null);
      }
    };

    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="health-badge" title={info ? `Model: ${info.model} | Embeddings: ${info.embedding_model}` : "API Status"}>
      <span
        className={`health-dot ${
          status === "ok" ? "health-ok" : status === "error" ? "health-error" : "health-checking"
        }`}
      />
      <span className="health-label">
        {status === "ok" ? "API Online" : status === "error" ? "API Offline" : "Checking..."}
      </span>
    </div>
  );
}
