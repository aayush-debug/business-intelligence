"use client";

import ChatPanel from "../chat-panel";

export default function ChatPage() {
  return (
    <main className="dashboard-container">
      <header className="dashboard-header" style={{ marginBottom: "20px" }}>
        <div>
          <h1 className="dashboard-title">AI Business Intelligence Assistant</h1>
          <p className="dashboard-subtitle">
            Ask natural language questions about your revenue, margins, customer loyalty, and stock risk.
          </p>
        </div>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "20px" }}>
        <ChatPanel />
      </div>

      <div className="grid-two-columns" style={{ marginTop: "24px" }}>
        <div className="card">
          <h3 style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-main)", marginBottom: "8px" }}>
            💡 What you can ask
          </h3>
          <ul style={{ paddingLeft: "18px", color: "var(--text-muted)", fontSize: "13.5px", lineHeight: "1.7" }}>
            <li><strong>Financials:</strong> &quot;What was my net profit and margin over the last 90 days?&quot;</li>
            <li><strong>Stock & Expiry:</strong> &quot;How much stock is expiring in the next 60 days?&quot;</li>
            <li><strong>Reordering:</strong> &quot;What medicines should I reorder from suppliers this week?&quot;</li>
            <li><strong>Competition:</strong> &quot;Compare Medora vs Curalife in Cetirizine 10mg.&quot;</li>
          </ul>
        </div>

        <div className="card">
          <h3 style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-main)", marginBottom: "8px" }}>
            🛡️ Strict Closed-Day Analytics Guarantee
          </h3>
          <p style={{ color: "var(--text-muted)", fontSize: "13.5px", lineHeight: "1.6" }}>
            The AI assistant only evaluates verified closed business days. Live, in-progress bills from open days
            are strictly excluded from revenue, profit, and customer ranking figures to prevent skewed metrics.
          </p>
        </div>
      </div>
    </main>
  );
}

