"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "../api";

function formatInr(val) {
  if (val === null || val === undefined || isNaN(val)) return "₹0";
  return "₹" + Math.round(val).toLocaleString("en-IN");
}

export default function DailySummariesPage() {
  const [summaries, setSummaries] = useState([]);
  const [selectedDay, setSelectedDay] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/api/day/summaries?limit=14`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load daily summaries");
        return res.json();
      })
      .then((data) => {
        setSummaries(data || []);
        if (data && data.length > 0) {
          loadDayDetail(data[0].date);
        }
        setLoading(false);
      })
      .catch((err) => {
        setErrorMessage(err.message || "Failed to load summaries");
        setLoading(false);
      });
  }, []);

  const loadDayDetail = (dateStr) => {
    setLoadingDetail(true);
    fetch(`${API_BASE}/api/day/summary?date=${dateStr}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((detail) => {
        setSelectedDay(detail);
        setLoadingDetail(false);
      })
      .catch(() => {
        setLoadingDetail(false);
      });
  };

  return (
    <main className="container">
      <header className="dashboard-header">
        <div className="header-title-group">
          <h1>Daily Summaries</h1>
          <p className="header-subtitle">
            Historical day-close reports and WhatsApp-ready daily business summaries.
          </p>
        </div>
        <div className="accountant-export-group">
          <a
            href={`${API_BASE}/api/reports/export/pdf?days=90`}
            target="_blank"
            rel="noreferrer"
            className="btn-export-accountant"
            title="Download official PDF financial statement for accountant"
          >
            📄 Accountant PDF
          </a>
          <a
            href={`${API_BASE}/api/reports/export/excel?days=90`}
            target="_blank"
            rel="noreferrer"
            className="btn-export-accountant"
            title="Download multi-sheet Excel file for accountant"
          >
            📊 Accountant Excel
          </a>
        </div>
      </header>

      {errorMessage && (
        <div className="error-banner">
          <strong>Error:</strong> {errorMessage}
        </div>
      )}

      {loading && <p className="loading-indicator">Loading closed days history…</p>}

      {!loading && summaries.length === 0 && (
        <div className="empty-state-card">
          <div style={{ fontSize: 44, marginBottom: 12 }}>📅</div>
          <div className="empty-state-title">No closed days yet</div>
          <div className="empty-state-desc">
            Days appear here after you close them on the Billing screen.
          </div>
        </div>
      )}

      {!loading && summaries.length > 0 && (
        <div className="grid-two-columns">
          {/* Left: List of recent closed days */}
          <section className="panel">
            <h2>Recent Closed Days (Last 14)</h2>
            <p className="panel-description">Click any date to inspect details and copy WhatsApp summary.</p>

            <div className="data-table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th className="num">Revenue</th>
                    <th className="num">Bills</th>
                    <th>vs Usual</th>
                  </tr>
                </thead>
                <tbody>
                  {summaries.map((s) => {
                    const isSelected = selectedDay?.date === s.date;
                    const vs = s.vs_usual_pct;
                    const isAbove = vs !== null && vs >= 0;

                    return (
                      <tr
                        key={s.date}
                        style={{
                          cursor: "pointer",
                          backgroundColor: isSelected ? "#f0f4f8" : "transparent",
                        }}
                        onClick={() => loadDayDetail(s.date)}
                      >
                        <td style={{ fontWeight: isSelected ? 700 : 500 }}>{s.date}</td>
                        <td className="num">{formatInr(s.revenue)}</td>
                        <td className="num">{s.invoices}</td>
                        <td>
                          {vs !== null ? (
                            <span style={{ color: isAbove ? "var(--profit)" : "var(--anomaly)", fontWeight: 600 }}>
                              {isAbove ? `+${vs}%` : `${vs}%`}
                            </span>
                          ) : (
                            <span style={{ color: "var(--text-muted)" }}>—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {/* Right: Detailed Day Report */}
          <section className="panel">
            {loadingDetail && <p className="loading-indicator">Loading day details…</p>}
            {!loadingDetail && selectedDay && (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
                  <div>
                    <h2 style={{ fontSize: 18, margin: 0 }}>Summary for {selectedDay.date}</h2>
                    <p className="panel-description" style={{ margin: "2px 0 0" }}>
                      Closed performance report
                    </p>
                  </div>
                  <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                    <a
                      href={`${API_BASE}/api/day/email-preview?date=${selectedDay.date}`}
                      target="_blank"
                      rel="noreferrer"
                      className="btn btn-secondary btn-sm"
                      title="Preview daily HTML email digest in browser"
                    >
                      📧 Preview Email
                    </a>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={async () => {
                        try {
                          const res = await fetch(`${API_BASE}/api/day/email-digest`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ date: selectedDay.date }),
                          });
                          const resData = await res.json();
                          if (res.ok) {
                            alert(`Daily digest dispatched for ${selectedDay.date} to ${resData.recipient}!`);
                          } else {
                            alert("Failed to send email digest: " + (resData.detail || "Server error"));
                          }
                        } catch (e) {
                          alert("Error sending digest: " + e.message);
                        }
                      }}
                      title="Dispatch daily email digest to store owner"
                    >
                      📤 Resend Email
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => {
                        navigator.clipboard.writeText(selectedDay.summary_text);
                        alert("Daily summary text copied to clipboard!");
                      }}
                    >
                      📋 Copy summary
                    </button>
                  </div>
                </div>

                <div className="summary-grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
                  <div className="summary-card">
                    <div className="summary-card-title">Day Revenue</div>
                    <div className="summary-card-val" style={{ color: "var(--revenue)" }}>
                      {formatInr(selectedDay.revenue)}
                    </div>
                    <div className="table-subtext">{selectedDay.invoices} bills entered</div>
                  </div>
                  <div className="summary-card">
                    <div className="summary-card-title">Gross Profit</div>
                    <div className="summary-card-val" style={{ color: "var(--profit)" }}>
                      {formatInr(selectedDay.gross_profit)}
                    </div>
                    <div className="table-subtext">{selectedDay.margin_pct}% gross margin</div>
                  </div>
                </div>

                <div style={{ background: "#f8fafc", padding: 16, borderRadius: 8, marginBottom: 16, border: "1px solid var(--border-color)", fontSize: 13.5 }}>
                  <div style={{ marginBottom: 8 }}>
                    <strong>Top Category:</strong> {selectedDay.top_category || "N/A"}
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    <strong>Best Sellers:</strong>{" "}
                    {selectedDay.top_products.map((p) => `${p.product} (${p.units} units)`).join(", ") || "None"}
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    <strong>Low Stock Alerts:</strong>{" "}
                    {selectedDay.low_stock?.count > 0 ? (
                      <span style={{ color: "var(--anomaly)" }}>
                        {selectedDay.low_stock.items.join(", ")} ({selectedDay.low_stock.count} items)
                      </span>
                    ) : (
                      "All stock levels healthy"
                    )}
                  </div>
                  <div>
                    <strong>Refills Due Tomorrow:</strong> {selectedDay.refills_due_tomorrow || 0}
                  </div>
                </div>

                <div>
                  <h3 style={{ fontSize: 13.5, margin: "0 0 6px", color: "var(--text-muted)" }}>
                    WhatsApp Text Preview:
                  </h3>
                  <pre
                    style={{
                      background: "#ffffff",
                      border: "1px solid var(--border-color)",
                      padding: 12,
                      borderRadius: 6,
                      fontSize: 12.5,
                      fontFamily: "inherit",
                      whiteSpace: "pre-wrap",
                      margin: 0,
                    }}
                  >
                    {selectedDay.summary_text}
                  </pre>
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
