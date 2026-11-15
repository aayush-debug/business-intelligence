"use client";

import { useEffect, useState } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

function formatInr(val) {
  if (val === null || val === undefined || isNaN(val)) return "₹0";
  return "₹" + Math.round(val).toLocaleString("en-IN");
}

export default function BillingPage() {
  const [products, setProducts] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [cart, setCart] = useState([]);
  const [companions, setCompanions] = useState([]);
  const [todayBillsCount, setTodayBillsCount] = useState(0);
  const [openDays, setOpenDays] = useState([]);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState("");
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // Close Day Modal State
  const [showCloseModal, setShowCloseModal] = useState(false);
  const [summaryData, setSummaryData] = useState(null);
  const [closing, setClosing] = useState(false);

  // Load products and day status
  const loadInitialData = async () => {
    try {
      const [prodsRes, statusRes] = await Promise.all([
        fetch(`${API_BASE}/api/top-products?days=0&limit=50`).then((r) => (r.ok ? r.json() : [])),
        fetch(`${API_BASE}/api/day/status`).then((r) => (r.ok ? r.json() : null)),
      ]);

      setProducts(prodsRes || []);

      if (statusRes) {
        setOpenDays(statusRes.open_days || []);
        const todayStr = statusRes.today;
        const todayOpen = (statusRes.open_days || []).find((d) => d.date === todayStr);
        setTodayBillsCount(todayOpen ? todayOpen.invoices : 0);
      }
    } catch (err) {
      console.error("Error loading billing data", err);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  // Whenever cart changes, fetch companion cross-sell suggestions
  useEffect(() => {
    if (cart.length === 0) {
      setCompanions([]);
      return;
    }

    const lastItem = cart[cart.length - 1];
    const pGroup = lastItem.category || lastItem.product;

    fetch(`${API_BASE}/api/basket/companions?product_group=${encodeURIComponent(pGroup)}&limit=3`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        if (Array.isArray(data)) setCompanions(data);
      })
      .catch(() => {});
  }, [cart]);

  const addToCart = (product) => {
    setCart((prev) => {
      const existing = prev.find((item) => item.product_id === product.product_id || item.product === product.product);
      if (existing) {
        return prev.map((item) =>
          item.product_id === existing.product_id ? { ...item, quantity: item.quantity + 1 } : item
        );
      }
      return [
        ...prev,
        {
          product_id: product.product_id || 1,
          product: product.product,
          category: product.category,
          unit_price: product.revenue && product.units ? product.revenue / product.units : 50.0,
          quantity: 1,
        },
      ];
    });
    setSearchTerm("");
  };

  const updateQuantity = (productId, delta) => {
    setCart((prev) =>
      prev
        .map((item) => {
          if (item.product_id === productId) {
            const newQty = item.quantity + delta;
            return newQty > 0 ? { ...item, quantity: newQty } : null;
          }
          return item;
        })
        .filter(Boolean)
    );
  };

  const totalBillAmount = cart.reduce((sum, item) => sum + item.quantity * item.unit_price, 0);

  const handleSaveBill = async () => {
    if (cart.length === 0) return;
    setSaving(true);
    setErrorMsg("");
    setSaveSuccessMsg("");

    try {
      const body = {
        customer_id: 1,
        items: cart.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
      };

      const res = await fetch(`${API_BASE}/api/sales/live`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to record live bill");
      }

      setSaveSuccessMsg(`Bill ${data.invoice_id} saved successfully! (${formatInr(data.total_amount)})`);
      setCart([]);
      setTodayBillsCount((prev) => prev + 1);
      loadInitialData();
    } catch (err) {
      setErrorMsg(err.message || "Failed to save bill.");
    } finally {
      setSaving(false);
    }
  };

  const handleCloseDay = async () => {
    const ok = window.confirm(
      "After closing, today's numbers appear on the dashboard and you cannot add bills to this date. Continue?"
    );
    if (!ok) return;

    setClosing(true);
    setErrorMsg("");

    try {
      const statusRes = await fetch(`${API_BASE}/api/day/status`).then((r) => r.json());
      const closeDate = statusRes.today;

      const res = await fetch(`${API_BASE}/api/day/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: closeDate }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to close day");
      }

      setSummaryData(data.summary);
      setShowCloseModal(true);
      loadInitialData();
    } catch (err) {
      setErrorMsg(err.message || "Failed to close day.");
    } finally {
      setClosing(false);
    }
  };

  const filteredProducts = searchTerm.trim()
    ? products.filter((p) => p.product.toLowerCase().includes(searchTerm.toLowerCase()))
    : [];

  return (
    <main className="container">
      <header className="dashboard-header">
        <div className="header-title-group">
          <h1>Point of Sale & Billing</h1>
          <p className="header-subtitle">
            Fast counter checkout. Add items and record sales with one click.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span className="nav-status-badge" style={{ fontSize: 13, padding: "6px 14px" }}>
            Bills entered today: <strong>{todayBillsCount}</strong>
          </span>
          <button
            type="button"
            className="btn btn-danger"
            onClick={handleCloseDay}
            disabled={closing}
          >
            {closing ? "Closing…" : "Close Day"}
          </button>
        </div>
      </header>

      {saveSuccessMsg && (
        <div style={{ background: "var(--success-bg)", color: "var(--success-text)", padding: "12px 16px", borderRadius: 8, marginBottom: 16, fontWeight: 600 }}>
          ✓ {saveSuccessMsg}
        </div>
      )}

      {errorMsg && (
        <div className="error-banner">
          <strong>Error:</strong> {errorMsg}
        </div>
      )}

      <div className="grid-two-columns">
        {/* Left Column: Product Search & Cart */}
        <section className="panel">
          <h2>Create Bill</h2>
          <p className="panel-description">Search product by name or click companion suggestions below.</p>

          {/* Product Search Box */}
          <div className="form-group" style={{ position: "relative" }}>
            <label className="form-label">Search Product</label>
            <input
              type="text"
              className="form-input"
              placeholder="Type medicine or product name…"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            {filteredProducts.length > 0 && (
              <div
                style={{
                  position: "absolute",
                  top: "100%",
                  left: 0,
                  right: 0,
                  backgroundColor: "#ffffff",
                  border: "1px solid var(--border-color)",
                  borderRadius: 6,
                  maxHeight: 220,
                  overflowY: "auto",
                  zIndex: 20,
                  boxShadow: "0 10px 15px -3px rgba(0,0,0,0.1)",
                }}
              >
                {filteredProducts.map((p) => (
                  <div
                    key={p.product}
                    style={{
                      padding: "10px 14px",
                      cursor: "pointer",
                      borderBottom: "1px solid var(--border-light)",
                      display: "flex",
                      justifyContent: "space-between",
                    }}
                    onClick={() => addToCart(p)}
                  >
                    <span>{p.product}</span>
                    <span style={{ color: "var(--revenue)", fontWeight: 600 }}>+ Add</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Companion Chips */}
          {companions.length > 0 && (
            <div style={{ margin: "16px 0" }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text-muted)" }}>
                Customers also buy:
              </div>
              <div className="chips-container">
                {companions.map((comp, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="chip"
                    onClick={() => {
                      addToCart({
                        product_id: comp.product_id || 1,
                        product: comp.companion_product,
                        category: comp.product_group,
                        units: 1,
                        revenue: 50.0,
                      });
                    }}
                  >
                    <span>+ {comp.companion_product}</span>
                    <span style={{ fontSize: 11, color: "var(--profit)", fontWeight: 700 }}>
                      {comp.lift}x
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Cart Table */}
          <div className="data-table-wrapper" style={{ marginTop: 20 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th className="num">Price</th>
                  <th className="num">Quantity</th>
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                {cart.length > 0 ? (
                  cart.map((item) => (
                    <tr key={item.product_id}>
                      <td style={{ fontWeight: 500 }}>{item.product}</td>
                      <td className="num">{formatInr(item.unit_price)}</td>
                      <td className="num">
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          style={{ padding: "2px 8px", marginRight: 6 }}
                          onClick={() => updateQuantity(item.product_id, -1)}
                        >
                          -
                        </button>
                        <span style={{ fontWeight: 600 }}>{item.quantity}</span>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          style={{ padding: "2px 8px", marginLeft: 6 }}
                          onClick={() => updateQuantity(item.product_id, 1)}
                        >
                          +
                        </button>
                      </td>
                      <td className="num" style={{ fontWeight: 600 }}>
                        {formatInr(item.quantity * item.unit_price)}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>
                      No items on this bill yet. Search and add products above.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Right Column: Customer & Checkout */}
        <section className="panel">
          <h2>Bill Summary</h2>
          <p className="panel-description">Review bill total and complete checkout.</p>

          <div style={{ background: "#f8fafc", padding: 20, borderRadius: 8, margin: "24px 0", border: "1px solid var(--border-color)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 14 }}>
              <span>Items in bill:</span>
              <span>{cart.reduce((s, i) => s + i.quantity, 0)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 20, fontWeight: 700, color: "var(--text-main)" }}>
              <span>Total Payable:</span>
              <span>{formatInr(totalBillAmount)}</span>
            </div>
          </div>

          <button
            type="button"
            className="btn btn-success"
            style={{ width: "100%", padding: "12px", fontSize: 16 }}
            onClick={handleSaveBill}
            disabled={cart.length === 0 || saving}
          >
            {saving ? "Saving…" : "Save Bill"}
          </button>
        </section>
      </div>

      {/* Close Day Summary Modal */}
      {showCloseModal && summaryData && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <h3>Day Closed Successfully</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setShowCloseModal(false)}
              >
                ×
              </button>
            </div>

            <div style={{ textAlign: "center", padding: "16px 0" }}>
              <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Total Day Revenue</div>
              <div style={{ fontSize: 36, fontWeight: 800, color: "var(--revenue)", margin: "4px 0" }}>
                {formatInr(summaryData.revenue)}
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-muted)" }}>
                from {summaryData.invoices} bills
                {summaryData.vs_usual_pct !== null && (
                  <span
                    style={{
                      marginLeft: 8,
                      color: summaryData.vs_usual_pct >= 0 ? "var(--profit)" : "var(--anomaly)",
                    }}
                  >
                    ({Math.abs(summaryData.vs_usual_pct)}%{" "}
                    {summaryData.vs_usual_pct >= 0 ? "above" : "below"} usual)
                  </span>
                )}
              </div>
            </div>

            <div style={{ borderTop: "1px solid var(--border-light)", borderBottom: "1px solid var(--border-light)", padding: "14px 0", margin: "14px 0", fontSize: 13.5 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span>Gross Profit:</span>
                <span style={{ fontWeight: 600 }}>
                  {formatInr(summaryData.gross_profit)} ({summaryData.margin_pct}%)
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span>Best Sellers:</span>
                <span style={{ fontWeight: 600 }}>
                  {summaryData.top_products.map((p) => p.product).join(", ") || "None"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Low Stock Items:</span>
                <span style={{ color: "var(--anomaly)", fontWeight: 600 }}>
                  {summaryData.low_stock?.count || 0} items
                </span>
              </div>
            </div>

            <div style={{ backgroundColor: "var(--success-bg)", border: "1px solid var(--border-color)", borderRadius: 6, padding: "10px 14px", marginTop: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "12.5px", color: "var(--success-text)", fontWeight: 600 }}>
                📧 Daily email digest dispatched to owner
              </span>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ padding: "4px 10px", fontSize: "12px", background: "#ffffff" }}
                onClick={() => window.open(`${API_BASE}/api/day/email-preview?date=${summaryData.date}`, "_blank")}
              >
                Preview Email ↗
              </button>
            </div>

            <div style={{ display: "flex", gap: 12, marginTop: 20 }}>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ flex: 1 }}
                onClick={() => {
                  navigator.clipboard.writeText(summaryData.summary_text);
                  alert("Daily summary text copied to clipboard!");
                }}
              >
                📋 Copy summary
              </button>
              <button
                type="button"
                className="btn btn-primary"
                style={{ flex: 1 }}
                onClick={() => setShowCloseModal(false)}
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
