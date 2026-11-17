"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "../api";

export default function RefillsPage() {
  const [refillsData, setRefillsData] = useState(null);
  const [activeTab, setActiveTab] = useState("due_soon");
  const [includeNames, setIncludeNames] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  const fetchRefills = () => {
    setLoading(true);
    setErrorMessage("");
    fetch(`${API_BASE}/api/refills?within_days=5&include_names=${includeNames}`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch refill reminders");
        return res.json();
      })
      .then((data) => {
        setRefillsData(data);
        setLoading(false);
      })
      .catch((err) => {
        setErrorMessage(err.message || "Failed to load refills");
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchRefills();
  }, [includeNames]);

  const handleCopyMessage = async (customerId) => {
    try {
      const res = await fetch(
        `${API_BASE}/api/refills/message?customer_id=${customerId}&include_names=${includeNames}`
      );
      const data = await res.json();
      if (data.text) {
        navigator.clipboard.writeText(data.text);
        alert("Message copied to clipboard!");
      }
    } catch {
      alert("Failed to copy message.");
    }
  };

  const handleOpenWhatsApp = async (customerId) => {
    try {
      const res = await fetch(
        `${API_BASE}/api/refills/message?customer_id=${customerId}&include_names=${includeNames}`
      );
      const data = await res.json();
      if (data.whatsapp_url) {
        window.open(data.whatsapp_url, "_blank");
      } else {
        alert("This customer does not have a phone number on file.");
      }
    } catch {
      alert("Failed to open WhatsApp.");
    }
  };

  const summary = refillsData?.summary || {
    due_soon: 0,
    overdue: 0,
    lapsed: 0,
    customers_due_soon: 0,
  };

  const filteredRows = (refillsData?.rows || []).filter((r) => r.status === activeTab);

  return (
    <main className="container">
      <header className="dashboard-header">
        <div className="header-title-group">
          <h1>Refill Reminders</h1>
          <p className="header-subtitle">
            Chronic care prescription cycle tracking based on 25-36 day recurring purchase patterns.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <label style={{ fontSize: 13.5, fontWeight: 500, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}>
            <input
              type="checkbox"
              checked={includeNames}
              onChange={(e) => setIncludeNames(e.target.checked)}
            />
            Include medicine names in messages
          </label>
        </div>
      </header>

      {/* Privacy Warning Banner */}
      <div style={{ background: "#f0f4f8", border: "1px solid var(--border-color)", padding: "10px 16px", borderRadius: 8, marginBottom: 20, fontSize: 13, color: "var(--text-muted)" }}>
        🔒 <strong>Owner Only:</strong> These lists contain private patient customer information. Keep this page confidential.
      </div>

      {errorMessage && (
        <div className="error-banner">
          <strong>Error:</strong> {errorMessage}
        </div>
      )}

      {/* Summary Cards */}
      <section className="summary-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        <div className="summary-card">
          <div className="summary-card-title">Due soon (within 5 days)</div>
          <div className="summary-card-val" style={{ color: "var(--revenue)" }}>
            {summary.due_soon}
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-card-title">Customers due soon</div>
          <div className="summary-card-val" style={{ color: "var(--revenue)" }}>
            {summary.customers_due_soon}
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-card-title">Overdue (1 - 60 days)</div>
          <div className="summary-card-val" style={{ color: "var(--anomaly)" }}>
            {summary.overdue}
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-card-title">Lapsed (&gt; 60 days)</div>
          <div className="summary-card-val" style={{ color: "#6b7280" }}>
            {summary.lapsed}
          </div>
        </div>
      </section>

      {/* Tabs */}
      <section className="panel">
        <div className="tabs-bar">
          <button
            type="button"
            className={`tab-btn ${activeTab === "due_soon" ? "active" : ""}`}
            onClick={() => setActiveTab("due_soon")}
          >
            Due soon ({summary.due_soon})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === "overdue" ? "active" : ""}`}
            onClick={() => setActiveTab("overdue")}
          >
            Overdue ({summary.overdue})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === "lapsed" ? "active" : ""}`}
            onClick={() => setActiveTab("lapsed")}
          >
            Lapsed ({summary.lapsed})
          </button>
        </div>

        {loading && <p className="loading-indicator">Loading refill schedules…</p>}

        {!loading && (
          <div className="data-table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Product</th>
                  <th>Last Bought</th>
                  <th>Expected Due</th>
                  <th>In Stock?</th>
                  <th className="num">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.length > 0 ? (
                  filteredRows.map((r, idx) => (
                    <tr key={idx}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{r.customer}</div>
                        <div className="table-subtext">{r.phone || "No phone registered"}</div>
                      </td>
                      <td>
                        <div>{r.product}</div>
                        <div className="table-subtext">Usually buys ~{r.usual_quantity} units</div>
                      </td>
                      <td>{r.last_purchase}</td>
                      <td>
                        <span style={{ fontWeight: 600 }}>{r.expected_due}</span>
                        <div className="table-subtext">
                          {r.days_overdue < 0
                            ? `In ${Math.abs(r.days_overdue)} days`
                            : r.days_overdue === 0
                            ? "Due today"
                            : `${r.days_overdue} days overdue`}
                        </div>
                      </td>
                      <td>
                        <span className={`badge ${r.in_stock ? "ok" : "drop"}`}>
                          {r.in_stock ? "In Stock" : "Out of Stock"}
                        </span>
                      </td>
                      <td className="num">
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          style={{ marginRight: 6 }}
                          onClick={() => handleCopyMessage(r.customer_id)}
                        >
                          📋 Copy
                        </button>
                        <button
                          type="button"
                          className="btn btn-success btn-sm"
                          disabled={!r.phone}
                          title={!r.phone ? "No phone number available" : "Open in WhatsApp"}
                          onClick={() => handleOpenWhatsApp(r.customer_id)}
                        >
                          💬 WhatsApp
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>
                      No customers found in this category.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
