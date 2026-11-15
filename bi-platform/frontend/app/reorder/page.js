"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

function formatInr(val) {
  if (val === null || val === undefined || isNaN(val)) return "₹0";
  return "₹" + Math.round(val).toLocaleString("en-IN");
}

export default function ReorderPage() {
  const [leadDays, setLeadDays] = useState(5);
  const [coverDays, setCoverDays] = useState(14);
  const [reorderData, setReorderData] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showDoNotReorder, setShowDoNotReorder] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/api/config`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setConfig(data);
      })
      .catch(() => {});
  }, []);

  const fetchReorder = () => {
    setLoading(true);
    setErrorMessage("");
    fetch(`${API_BASE}/api/reorder/suggestions?lead_days=${leadDays}&cover_days=${coverDays}`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch reorder suggestions");
        return res.json();
      })
      .then((data) => {
        setReorderData(data);
        setLoading(false);
      })
      .catch((err) => {
        setErrorMessage(err.message || "Failed to load reorder data");
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchReorder();
  }, [leadDays, coverDays]);

  const copyWhatsAppText = () => {
    if (!reorderData || !reorderData.lines.length) return;

    let text = `📦 Purchase Order Suggestions (${new Date().toLocaleDateString("en-IN")})\n`;
    text += `Target stock: ${leadDays}d delivery + ${coverDays}d cover\n`;
    text += `Total estimated cost: ${formatInr(reorderData.total_cost)}\n\n`;

    (reorderData.by_manufacturer || []).forEach((mfrGroup) => {
      text += `--- ${mfrGroup.manufacturer} (Subtotal: ${formatInr(mfrGroup.total_cost)}) ---\n`;
      const mfrLines = reorderData.lines.filter((l) => l.manufacturer === mfrGroup.manufacturer);
      mfrLines.forEach((line) => {
        text += `• ${line.product}: ${line.suggested_qty} units @ ${formatInr(line.unit_cost)} = ${formatInr(line.line_cost)}\n`;
      });
      text += `\n`;
    });

    navigator.clipboard.writeText(text);
    alert("Purchase list copied to clipboard formatted for WhatsApp!");
  };

  const isEmptyInventory = !reorderData || (reorderData.lines.length === 0 && reorderData.do_not_reorder.length === 0);

  return (
    <main className="container">
      <header className="dashboard-header">
        <div className="header-title-group">
          <h1>Reorder Suggestions</h1>
          <p className="header-subtitle">
            Automated stock purchase recommendations based on 60-day sales demand and delivery lead times.
          </p>
        </div>
        {reorderData && reorderData.lines.length > 0 && (
          <div style={{ display: "flex", gap: 10 }}>
            <a
              href={`${API_BASE}/api/reorder/export.csv?lead_days=${leadDays}&cover_days=${coverDays}`}
              download="reorder_suggestions.csv"
              className="btn btn-secondary"
            >
              📥 Download purchase list (CSV)
            </a>
            <button
              type="button"
              className="btn btn-primary"
              onClick={copyWhatsAppText}
            >
              📋 Copy as text (WhatsApp)
            </button>
          </div>
        )}
      </header>

      {/* Control Inputs */}
      <section className="panel" style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <label className="form-label" style={{ margin: 0 }}>
              Delivery time (days):
            </label>
            {config?.snapshot_mode ? (
              <select
                className="form-input"
                style={{ width: 100 }}
                value={leadDays}
                onChange={(e) => setLeadDays(Number(e.target.value))}
              >
                <option value={3}>3 days</option>
                <option value={5}>5 days</option>
                <option value={7}>7 days</option>
                <option value={10}>10 days</option>
              </select>
            ) : (
              <input
                type="number"
                min={1}
                max={30}
                className="form-input"
                style={{ width: 80 }}
                value={leadDays}
                onChange={(e) => setLeadDays(Math.max(1, Number(e.target.value)))}
              />
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <label className="form-label" style={{ margin: 0 }}>
              Days of stock to buy for:
            </label>
            {config?.snapshot_mode ? (
              <select
                className="form-input"
                style={{ width: 100 }}
                value={coverDays}
                onChange={(e) => setCoverDays(Number(e.target.value))}
              >
                <option value={7}>7 days</option>
                <option value={14}>14 days</option>
                <option value={21}>21 days</option>
                <option value={30}>30 days</option>
              </select>
            ) : (
              <input
                type="number"
                min={3}
                max={60}
                className="form-input"
                style={{ width: 80 }}
                value={coverDays}
                onChange={(e) => setCoverDays(Math.max(3, Number(e.target.value)))}
              />
            )}
          </div>
          {reorderData && (
            <div style={{ marginLeft: "auto", fontSize: 16, fontWeight: 700 }}>
              Grand Total: <span style={{ color: "var(--revenue)" }}>{formatInr(reorderData.total_cost)}</span>
            </div>
          )}
        </div>
      </section>

      {errorMessage && (
        <div className="error-banner">
          <strong>Error:</strong> {errorMessage}
        </div>
      )}

      {loading && <p className="loading-indicator">Computing reorder quantities…</p>}

      {isEmptyInventory && !loading && (
        <div className="empty-state-card">
          <div style={{ fontSize: 44, marginBottom: 12 }}>📦</div>
          <div className="empty-state-title">No inventory data uploaded</div>
          <div className="empty-state-desc">
            To generate automatic reorder suggestions, upload your current inventory stock and recent sales.
          </div>
          <Link href="/data" className="btn btn-primary">
            Upload Inventory →
          </Link>
        </div>
      )}

      {reorderData && !isEmptyInventory && (
        <>
          {/* Results grouped by manufacturer */}
          {reorderData.by_manufacturer.map((mfrGroup) => {
            const mfrLines = reorderData.lines.filter((l) => l.manufacturer === mfrGroup.manufacturer);
            if (!mfrLines.length) return null;

            return (
              <section key={mfrGroup.manufacturer} className="panel">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                  <h2 style={{ margin: 0, fontSize: 16 }}>{mfrGroup.manufacturer}</h2>
                  <span style={{ fontSize: 14, fontWeight: 700, color: "var(--text-main)" }}>
                    Subtotal: {formatInr(mfrGroup.total_cost)} ({mfrGroup.items} items)
                  </span>
                </div>

                <div className="data-table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th className="num">Stock on Hand</th>
                        <th className="num">Avg Daily Units</th>
                        <th className="num">Days of Supply</th>
                        <th className="num">Suggested Qty</th>
                        <th className="num">Unit Cost</th>
                        <th className="num">Line Cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mfrLines.map((line) => (
                        <tr key={line.product}>
                          <td style={{ fontWeight: 500 }}>{line.product}</td>
                          <td className="num">{line.stock_on_hand}</td>
                          <td className="num">{line.avg_daily}</td>
                          <td className="num">{line.days_of_cover ? `${Math.round(line.days_of_cover)}d` : "—"}</td>
                          <td className="num" style={{ fontWeight: 700, color: "var(--revenue)" }}>
                            {line.suggested_qty}
                          </td>
                          <td className="num">{formatInr(line.unit_cost)}</td>
                          <td className="num" style={{ fontWeight: 600 }}>
                            {formatInr(line.line_cost)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            );
          })}

          {reorderData.lines.length === 0 && (
            <div className="panel" style={{ textAlign: "center", padding: "32px 20px" }}>
              <div style={{ fontSize: 16, fontWeight: 600, color: "var(--success-text)", marginBottom: 6 }}>
                ✓ All stock levels are sufficient
              </div>
              <p className="panel-description" style={{ margin: 0 }}>
                No products currently require reordering for {leadDays + coverDays} days of coverage.
              </p>
            </div>
          )}

          {/* Collapsed Do Not Reorder section */}
          {reorderData.do_not_reorder && reorderData.do_not_reorder.length > 0 && (
            <section className="panel" style={{ borderStyle: "dashed", marginTop: 24 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <h2 style={{ fontSize: 15, margin: 0 }}>Not recommended to reorder</h2>
                  <p className="panel-description" style={{ margin: "4px 0 0" }}>
                    {reorderData.do_not_reorder.length} items skipped due to overstock, near expiry, or zero recent demand.
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setShowDoNotReorder(!showDoNotReorder)}
                >
                  {showDoNotReorder ? "Hide list" : "Show reasons"}
                </button>
              </div>

              {showDoNotReorder && (
                <div className="data-table-wrapper" style={{ marginTop: 16 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th>Reason Skipped</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reorderData.do_not_reorder.map((item, idx) => (
                        <tr key={idx}>
                          <td style={{ fontWeight: 500 }}>{item.product}</td>
                          <td style={{ color: "var(--text-muted)" }}>{item.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </main>
  );
}
