"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import {
  ResponsiveContainer,
  ComposedChart,
  LineChart,
  BarChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

const DATE_RANGES = [
  { label: "30 days", value: 30 },
  { label: "90 days", value: 90 },
  { label: "1 year", value: 365 },
  { label: "All time", value: 0 },
];

const BRAND_COLORS = ["#3b4cca", "#0f9d8a", "#e29a00", "#8b5cf6", "#ec4899", "#06b6d4"];

function formatInr(val) {
  if (val === null || val === undefined || isNaN(val)) return "₹0";
  return "₹" + Math.round(val).toLocaleString("en-IN");
}

function formatShortInr(val) {
  if (val === null || val === undefined || isNaN(val)) return "0";
  const abs = Math.abs(val);
  const sign = val < 0 ? "-" : "";
  if (abs >= 1e7) return sign + (abs / 1e7).toFixed(1) + "Cr";
  if (abs >= 1e5) return sign + (abs / 1e5).toFixed(1) + "L";
  if (abs >= 1e3) return sign + (abs / 1e3).toFixed(0) + "k";
  return sign + abs.toString();
}

async function fetchEndpoint(path) {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request to ${url} failed with status ${response.status}`);
  }
  return response.json();
}

function GrowthIndicator({ value, show }) {
  if (!show || value === null || value === undefined) {
    return <div className="kpi-growth-placeholder" />;
  }
  const isPositive = value >= 0;
  const arrow = isPositive ? "↑" : "↓";
  return (
    <div className={`kpi-growth ${isPositive ? "up" : "down"}`}>
      {arrow} {Math.abs(value).toFixed(1)}% vs previous period
    </div>
  );
}

export default function BusinessOverviewPage() {
  const [days, setDays] = useState(90);
  const [data, setData] = useState(null);
  const [dataStatus, setDataStatus] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [brands, setBrands] = useState([]);
  const [inventory, setInventory] = useState(null);
  const [profitLeaks, setProfitLeaks] = useState(null);
  const [basketPairs, setBasketPairs] = useState(null);
  const [showAllBrands, setShowAllBrands] = useState(false);
  const [stockTab, setStockTab] = useState("reorder");
  const [loading, setLoading] = useState(true);
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const handleLoadDemoData = async (force = false) => {
    setLoadingDemo(true);
    setErrorMessage("");
    try {
      const url = force ? `${API_BASE}/api/demo/load?force=true` : `${API_BASE}/api/demo/load`;
      const res = await fetch(url, { method: "POST" });
      const resData = await res.json();
      if (!res.ok) {
        throw new Error(resData.detail || "Failed to load demo data");
      }
      window.location.reload();
    } catch (err) {
      setErrorMessage(err.message || "Failed to load demo data.");
      setLoadingDemo(false);
    }
  };

  const handleResetData = async () => {
    if (!window.confirm("This will clear all loaded data so you can upload your own business files from scratch. Continue?")) return;
    setResetting(true);
    setErrorMessage("");
    try {
      const res = await fetch(`${API_BASE}/api/data/reset`, { method: "POST" });
      const resData = await res.json();
      if (!res.ok) {
        throw new Error(resData.detail || "Failed to reset data");
      }
      window.location.href = "/data";
    } catch (err) {
      setErrorMessage(err.message || "Failed to reset data.");
      setResetting(false);
    }
  };

  const requestIdRef = useRef(0);

  // Fetch static or range-independent datasets
  useEffect(() => {
    let isCurrent = true;
    fetchEndpoint("/api/data/status")
      .then((st) => { if (isCurrent) setDataStatus(st); })
      .catch(() => {});

    fetchEndpoint("/api/forecast")
      .then((fc) => { if (isCurrent) setForecast(fc); })
      .catch(() => {});

    fetchEndpoint("/api/inventory/status")
      .then((inv) => { if (isCurrent) setInventory(inv); })
      .catch(() => {});

    return () => { isCurrent = false; };
  }, []);

  // Fetch range-dependent datasets
  useEffect(() => {
    const currentRequestId = ++requestIdRef.current;
    setLoading(true);
    setErrorMessage("");

    const granularity = days === 30 ? "day" : days === 90 ? "week" : "month";

    Promise.all([
      fetchEndpoint(`/api/kpis?days=${days}`),
      fetchEndpoint(`/api/trend?granularity=${granularity}&days=${days}`),
      fetchEndpoint(`/api/top-products?days=${days}&limit=8`),
      fetchEndpoint(`/api/categories?days=${days}`),
      fetchEndpoint(`/api/anomalies?days=${days}`),
      fetchEndpoint(`/api/brands/comparison?days=${days}`),
      fetchEndpoint(`/api/profit/leaks?days=${days}`),
      fetchEndpoint(`/api/basket/pairs?days=${days}&min_count=20&limit=10`),
    ])
      .then(([kpis, trend, products, categories, anomalies, brandsData, leaksData, basketData]) => {
        if (currentRequestId === requestIdRef.current) {
          setData({ kpis, trend, products, categories, anomalies });
          setBrands(brandsData || []);
          setProfitLeaks(leaksData);
          setBasketPairs(basketData);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (currentRequestId === requestIdRef.current) {
          setErrorMessage(err.message || "Failed to load dashboard data");
          setLoading(false);
        }
      });
  }, [days]);

  const isEmpty = data && data.kpis.orders === 0 && data.kpis.revenue === 0;
  const isMockData = Boolean(dataStatus?.is_mock_data || (dataStatus?.products?.rows === 54 && dataStatus?.customers?.rows === 420));

  return (
    <main className="container">
      {/* 1. Header */}
      <header className="dashboard-header">
        <div className="header-title-group">
          <h1>Business overview</h1>
          <p className="header-subtitle">Performance, profit trends, forecast, and operational anomalies.</p>
        </div>
        {!isEmpty && (
          <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
            <div className="accountant-export-group">
              <a
                href={`${API_BASE}/api/reports/export/pdf?days=${days}`}
                target="_blank"
                rel="noreferrer"
                className="btn-export-accountant"
                title="Download official PDF financial statement for accountant"
              >
                📄 Accountant PDF
              </a>
              <a
                href={`${API_BASE}/api/reports/export/excel?days=${days}`}
                target="_blank"
                rel="noreferrer"
                className="btn-export-accountant"
                title="Download multi-sheet Excel file for accountant"
              >
                📊 Accountant Excel
              </a>
            </div>
            <nav className="segmented-control" aria-label="Select date range">
              {DATE_RANGES.map((range) => (
                <button
                  key={range.value}
                  type="button"
                  className={days === range.value ? "active" : ""}
                  onClick={() => setDays(range.value)}
                  aria-pressed={days === range.value}
                >
                  {range.label}
                </button>
              ))}
            </nav>
          </div>
        )}
      </header>

      {/* Data Source Chooser Bar (shown when data is present) */}
      {!isEmpty && data && (
        <section
          style={{
            background: isMockData ? "rgba(239, 246, 255, 0.6)" : "#ffffff",
            border: isMockData ? "1px solid #bfdbfe" : "1px solid var(--border-color)",
            borderRadius: "8px",
            padding: "10px 16px",
            marginBottom: "20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span
              style={{
                fontSize: "12px",
                fontWeight: 700,
                padding: "3px 9px",
                borderRadius: "5px",
                background: isMockData ? "#dbeafe" : "#dcfce7",
                color: isMockData ? "#1e40af" : "#166534",
                border: `1px solid ${isMockData ? "#93c5fd" : "#86efac"}`,
              }}
            >
              {isMockData ? "🧪 Mock Demo Data Active" : "📊 Your Custom Business Data Active"}
            </span>
            <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>
              {isMockData
                ? "Currently checking pre-configured pharmacy data (54 products, 94.6k sales). Want to test with your own store files?"
                : "Displaying metrics from your uploaded datasets. You can upload more files or switch to sample data."}
            </span>
          </div>

          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <Link href="/data" className="btn btn-primary btn-sm" style={{ padding: "6px 14px", fontSize: "13px" }}>
              📤 Upload your own data →
            </Link>
            {isMockData ? (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleResetData}
                disabled={resetting}
                title="Wipe mock data and start with an empty database to upload your files"
                style={{ padding: "6px 12px", fontSize: "13px" }}
              >
                {resetting ? "Clearing…" : "🧹 Clear & upload own data"}
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => handleLoadDemoData(true)}
                disabled={loadingDemo}
                title="Reload the 2-year sample pharmacy dataset"
                style={{ padding: "6px 12px", fontSize: "13px" }}
              >
                {loadingDemo ? "Loading…" : "🧪 Check mock data"}
              </button>
            )}
          </div>
        </section>
      )}

      {/* Error state */}
      {errorMessage && (
        <div className="error-banner" role="alert">
          <strong>Unable to load dashboard data</strong>
          <div>
            Error connecting to <code>{API_BASE}</code>: {errorMessage}. Please verify backend server is running.
          </div>
        </div>
      )}

      {/* Loading state message */}
      {loading && !data && <p className="loading-indicator">Loading your numbers…</p>}

      {/* Empty State: Side-by-side Choice Cards */}
      {isEmpty && (
        <div style={{ margin: "20px 0" }}>
          <div style={{ textAlign: "center", marginBottom: "22px" }}>
            <h2 style={{ fontSize: "22px", fontWeight: 700, color: "var(--text-main)", marginBottom: "6px" }}>
              Welcome to Company Brain
            </h2>
            <p style={{ color: "var(--text-muted)", fontSize: "14px", margin: 0 }}>
              Choose whether you would like to explore sample mock data or upload your own store records:
            </p>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px" }}>
            {/* Card 1: Check Mock Data */}
            <div
              className="panel"
              style={{
                padding: "24px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                border: "2px solid #3b82f6",
                borderRadius: "10px",
                background: "linear-gradient(180deg, #f0f7ff 0%, #ffffff 100%)",
              }}
            >
              <div>
                <div style={{ fontSize: "36px", marginBottom: "10px" }}>🧪</div>
                <h3 style={{ fontSize: "18px", fontWeight: 700, color: "#1e3a8a", marginBottom: "8px" }}>
                  Option 1: Check Mock Data
                </h3>
                <p style={{ color: "var(--text-muted)", fontSize: "13.5px", lineHeight: "1.6", marginBottom: "16px" }}>
                  Instantly explore 2 years of simulated pharmacy sales with 54 medicines, profit margins, inventory reordering, anomaly detection, and the AI chatbot.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => handleLoadDemoData(false)}
                disabled={loadingDemo}
                style={{ width: "100%", justifyContent: "center", padding: "10px" }}
              >
                {loadingDemo ? "Loading test data…" : "🚀 Load & Explore Mock Data"}
              </button>
            </div>

            {/* Card 2: Upload Own Data */}
            <div
              className="panel"
              style={{
                padding: "24px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                border: "2px solid var(--border-color)",
                borderRadius: "10px",
                background: "var(--panel-bg)",
              }}
            >
              <div>
                <div style={{ fontSize: "36px", marginBottom: "10px" }}>📤</div>
                <h3 style={{ fontSize: "18px", fontWeight: 700, color: "var(--text-main)", marginBottom: "8px" }}>
                  Option 2: Upload Your Own Data
                </h3>
                <p style={{ color: "var(--text-muted)", fontSize: "13.5px", lineHeight: "1.6", marginBottom: "16px" }}>
                  Import your actual business files (CSV or Excel) for Products, Sales history, Current stock, and Expenses to compute custom insights and reports.
                </p>
              </div>
              <Link
                href="/data"
                className="btn btn-secondary"
                style={{ width: "100%", justifyContent: "center", padding: "10px" }}
              >
                📂 Go to Upload Data →
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Dashboard Content */}
      {data && !isEmpty && (
        <>
          {/* 2. KPI Strip */}
          <section className="kpi-strip" aria-label="Key performance indicators">
            <div className="kpi-cell">
              <div className="kpi-label">Revenue</div>
              <div className="kpi-value">{formatInr(data.kpis.revenue)}</div>
              <GrowthIndicator value={data.kpis.revenue_growth} show={days !== 0} />
            </div>
            <div className="kpi-cell">
              <div className="kpi-label">Net profit</div>
              <div className="kpi-value">{formatInr(data.kpis.net_profit)}</div>
              <GrowthIndicator value={data.kpis.profit_growth} show={days !== 0} />
            </div>
            <div className="kpi-cell">
              <div className="kpi-label">Profit margin</div>
              <div className="kpi-value">{(data.kpis.margin || 0).toFixed(1)}%</div>
              <div className="kpi-growth-placeholder" />
            </div>
            <div className="kpi-cell">
              <div className="kpi-label">Orders</div>
              <div className="kpi-value">{(data.kpis.orders || 0).toLocaleString("en-IN")}</div>
              <div className="kpi-growth-placeholder" />
            </div>
            <div className="kpi-cell">
              <div className="kpi-label">Average order value</div>
              <div className="kpi-value">{formatInr(data.kpis.aov)}</div>
              <div className="kpi-growth-placeholder" />
            </div>
          </section>

          {/* 3. Line Chart: Revenue & Gross Profit over time */}
          <section className="panel">
            <h2>Revenue and gross profit</h2>
            <p className="panel-description">Revenue and gross profit over time. Gross profit reflects total sales minus cost of goods sold.</p>
            <div style={{ width: "100%", height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.trend} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="#e6eaef" vertical={false} />
                  <XAxis dataKey="period" tick={{ fontSize: 12, fill: "#5b6b7f" }} minTickGap={35} />
                  <YAxis tickFormatter={formatShortInr} tick={{ fontSize: 12, fill: "#5b6b7f" }} width={54} />
                  <Tooltip
                    formatter={(val) => [formatInr(val)]}
                    contentStyle={{ backgroundColor: "#ffffff", border: "1px solid #d9dfe6", borderRadius: 6, fontSize: 13 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 13, paddingTop: 10 }} />
                  <Line type="monotone" dataKey="revenue" name="Revenue" stroke="#3b4cca" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="profit" name="Gross profit" stroke="#0f9d8a" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>

          {/* 4. Forecast & Unusual Days */}
          <section className="grid-two-columns">
            {/* Column A: Forecast Chart */}
            <div className="panel">
              <h2>Forecast (next 30 days)</h2>
              {forecast && forecast.forecast?.length > 0 ? (
                <>
                  <p className="panel-description">
                    Total expected revenue is {formatInr(forecast.total_forecast)}. Model MAE: {formatInr(forecast.backtest.model_mae)}.
                  </p>
                  <div style={{ width: "100%", height: 260 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart
                        data={[
                          ...(forecast.history || []).map((h) => ({ date: h.date, actual: h.actual })),
                          ...(forecast.forecast || []).map((f) => ({
                            date: f.date,
                            forecast: f.forecast,
                            lower: f.lower,
                            upper: f.upper,
                          })),
                        ]}
                        margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                      >
                        <CartesianGrid stroke="#e6eaef" vertical={false} />
                        <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#5b6b7f" }} minTickGap={35} />
                        <YAxis tickFormatter={formatShortInr} tick={{ fontSize: 11, fill: "#5b6b7f" }} width={50} />
                        <Tooltip
                          formatter={(val) => [formatInr(val)]}
                          contentStyle={{ backgroundColor: "#ffffff", border: "1px solid #d9dfe6", borderRadius: 6, fontSize: 12 }}
                        />
                        <Line type="monotone" dataKey="actual" name="Actual sales" stroke="#14213d" strokeWidth={1.5} dot={false} />
                        <Line type="monotone" dataKey="forecast" name="Projected" stroke="#e29a00" strokeWidth={2} strokeDasharray="3 3" dot={false} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </>
              ) : (
                <p className="empty-notice">Forecast requires at least 35 days of sales history.</p>
              )}
            </div>

            {/* Column B: Unusual Days Table */}
            <div className="panel">
              <h2>Unusual days & AI Explanations</h2>
              <p className="panel-description">
                Spikes and drops detected via weekday-normalized rolling z-scores with AI driver explanations.
              </p>
              {data.anomalies.flagged && data.anomalies.flagged.length > 0 ? (
                <div className="data-table-wrapper" style={{ maxHeight: 320, overflowY: "auto" }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th className="num">Revenue</th>
                        <th className="num">Z-Score</th>
                        <th>Type</th>
                        <th>AI &quot;Why&quot; Explanation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.anomalies.flagged.map((row) => (
                        <tr key={row.date}>
                          <td style={{ whiteSpace: "nowrap", fontWeight: 600 }}>{row.date}</td>
                          <td className="num">{formatInr(row.revenue)}</td>
                          <td className="num">{row.z > 0 ? `+${row.z.toFixed(2)}` : row.z.toFixed(2)}</td>
                          <td>
                            <span className={`badge ${row.type}`}>{row.type}</span>
                          </td>
                          <td style={{ fontSize: "12px", color: "var(--text-main)", minWidth: "240px", lineHeight: "1.45" }}>
                            {row.explanation ? (
                              <div className="anomaly-why-box">
                                {row.explanation}
                              </div>
                            ) : (
                              <span style={{ color: "var(--text-muted)" }}>Evaluating day top sellers...</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="empty-notice">No unusual revenue spikes or drops flagged in this period.</p>
              )}
            </div>
          </section>

          {/* 5. Categories & Top Products */}
          <section className="grid-two-columns">
            <div className="panel">
              <h2>Revenue by category</h2>
              <p className="panel-description">Sales distribution across product categories.</p>
              <div style={{ width: "100%", height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.categories} layout="vertical" margin={{ top: 5, right: 20, left: 30, bottom: 5 }}>
                    <CartesianGrid stroke="#e6eaef" horizontal={false} />
                    <XAxis type="number" tickFormatter={formatShortInr} tick={{ fontSize: 11, fill: "#5b6b7f" }} />
                    <YAxis dataKey="category" type="category" tick={{ fontSize: 11, fill: "#14213d" }} width={90} />
                    <Tooltip
                      formatter={(val) => [formatInr(val)]}
                      contentStyle={{ backgroundColor: "#ffffff", border: "1px solid #d9dfe6", borderRadius: 6, fontSize: 12 }}
                    />
                    <Bar dataKey="revenue" name="Revenue" fill="#3b4cca" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="panel">
              <h2>Top products</h2>
              <p className="panel-description">Bestsellers by revenue and profit margin.</p>
              <div className="data-table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th className="num">Revenue</th>
                      <th className="num">Units</th>
                      <th className="num">Margin</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.products.map((p) => (
                      <tr key={p.product}>
                        <td>
                          <div>{p.product}</div>
                          <div className="table-subtext">{p.category}</div>
                        </td>
                        <td className="num">{formatInr(p.revenue)}</td>
                        <td className="num">{p.units.toLocaleString("en-IN")}</td>
                        <td className="num">{p.margin_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          {/* 6. NEW: Brand Comparison */}
          {brands.length > 0 && (
            <section className="panel">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <div>
                  <h2>Brand comparison</h2>
                  <p className="panel-description" style={{ margin: 0 }}>
                    Comparing competing brands within product groups to highlight imbalance and opportunities.
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setShowAllBrands(!showAllBrands)}
                >
                  {showAllBrands ? "Hide table" : "Show all groups"}
                </button>
              </div>

              {/* Stacked bars for top 5 most imbalanced groups */}
              <div style={{ marginTop: 16 }}>
                {brands.slice(0, 5).map((group) => {
                  return (
                    <div key={group.product_group} className="brand-group-block">
                      <div className="brand-group-header">
                        <span className="brand-group-title">{group.product_group}</span>
                        <span className="brand-group-meta">
                          {group.total_units} units sold • {formatInr(group.total_revenue)}
                        </span>
                      </div>

                      {/* Stacked bar */}
                      <div className="stacked-bar-container">
                        {group.brands.map((b, idx) => (
                          <div
                            key={b.product}
                            className="stacked-bar-segment"
                            style={{
                              width: `${Math.max(b.share_pct, 4)}%`,
                              backgroundColor: BRAND_COLORS[idx % BRAND_COLORS.length],
                            }}
                            title={`${b.product}: ${b.units} units (${b.share_pct}%)`}
                          >
                            {b.manufacturer || b.product} ({b.share_pct}%)
                          </div>
                        ))}
                      </div>

                      {group.insight && <div className="brand-insight-text">💡 {group.insight}</div>}
                    </div>
                  );
                })}
              </div>

              {/* Collapsible full table */}
              {showAllBrands && (
                <div className="data-table-wrapper" style={{ marginTop: 20 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Group / Brand</th>
                        <th>Manufacturer</th>
                        <th className="num">Units Sold</th>
                        <th className="num">Share</th>
                        <th className="num">Margin</th>
                        <th className="num">Stock on Hand</th>
                        <th className="num">Days of Supply</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {brands.map((g) =>
                        g.brands.map((b) => (
                          <tr key={`${g.product_group}-${b.product}`}>
                            <td>
                              <div>{b.product}</div>
                              <div className="table-subtext">{g.product_group}</div>
                            </td>
                            <td>{b.manufacturer}</td>
                            <td className="num">{b.units}</td>
                            <td className="num">{b.share_pct}%</td>
                            <td className="num">{b.margin_pct}%</td>
                            <td className="num">{b.stock_on_hand}</td>
                            <td className="num">{b.days_of_cover ? `${Math.round(b.days_of_cover)}d` : "—"}</td>
                            <td>
                              {b.flag ? (
                                <span className={`badge ${b.flag}`}>{b.flag}</span>
                              ) : (
                                <span style={{ color: "#9ca3af" }}>—</span>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          {/* 7. NEW: Stock Alerts */}
          <section className="panel">
            <h2>Stock alerts</h2>
            <p className="panel-description">Monitor low stock, overstocked capital, and upcoming expiry batches.</p>

            {inventory ? (
              <>
                <div className="summary-grid">
                  <div className="summary-card">
                    <div className="summary-card-title">Money tied up in overstock</div>
                    <div className="summary-card-val">{formatInr(inventory.summary.capital_tied_up_overstock)}</div>
                  </div>
                  <div className="summary-card">
                    <div className="summary-card-title">Stock expiring soon (60d)</div>
                    <div className="summary-card-val">{formatInr(inventory.summary.value_expiring_soon)}</div>
                  </div>
                  <div className="summary-card">
                    <div className="summary-card-title">Items needing reorder</div>
                    <div className="summary-card-val" style={{ color: "var(--anomaly)" }}>
                      {inventory.summary.items_to_reorder}
                    </div>
                  </div>
                </div>

                <div className="tabs-bar">
                  <button
                    type="button"
                    className={`tab-btn ${stockTab === "reorder" ? "active" : ""}`}
                    onClick={() => setStockTab("reorder")}
                  >
                    Reorder soon
                  </button>
                  <button
                    type="button"
                    className={`tab-btn ${stockTab === "overstocked" ? "active" : ""}`}
                    onClick={() => setStockTab("overstocked")}
                  >
                    Overstocked
                  </button>
                  <button
                    type="button"
                    className={`tab-btn ${stockTab === "expiring_soon" ? "active" : ""}`}
                    onClick={() => setStockTab("expiring_soon")}
                  >
                    Expiring soon
                  </button>
                </div>

                <div className="data-table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th>Manufacturer</th>
                        <th className="num">Stock on Hand</th>
                        <th className="num">Avg Daily Units</th>
                        <th className="num">Days of Cover</th>
                        <th className="num">Stock Value</th>
                        <th>Nearest Expiry</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inventory.products
                        .filter((p) => p.status === stockTab)
                        .map((p) => (
                          <tr key={p.product_id}>
                            <td>{p.product}</td>
                            <td>{p.manufacturer}</td>
                            <td className="num">{p.stock_on_hand}</td>
                            <td className="num">{p.avg_daily_units}</td>
                            <td className="num">{p.days_of_cover ? `${Math.round(p.days_of_cover)}d` : "—"}</td>
                            <td className="num">{formatInr(p.stock_value)}</td>
                            <td>
                              {p.nearest_expiry ? (
                                <span>
                                  {p.nearest_expiry} ({p.days_to_expiry}d)
                                </span>
                              ) : (
                                "—"
                              )}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                  {inventory.products.filter((p) => p.status === stockTab).length === 0 && (
                    <p className="empty-notice" style={{ padding: "16px 0", textAlign: "center" }}>
                      No items currently in this status.
                    </p>
                  )}
                </div>
              </>
            ) : (
              <p className="empty-notice">
                No inventory data uploaded yet. <Link href="/data">Upload inventory stock rows →</Link>
              </p>
            )}
          </section>

          {/* 8. NEW: Where Profit is Leaking */}
          {profitLeaks && (
            <section className="panel">
              <h2>Where profit is leaking</h2>
              <p className="panel-description">
                Uncover discounts given, brand margin gaps, low-margin bestsellers, and expired stock losses.
              </p>

              <div className="grid-two-columns" style={{ marginBottom: 20 }}>
                {/* 1. Discount Leakage */}
                <div className="summary-card">
                  <h3 style={{ margin: "0 0 6px", fontSize: 15 }}>1. Discount leakage</h3>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text-main)", marginBottom: 4 }}>
                    {profitLeaks.discount_leakage.headline}
                  </div>
                  <div className="table-subtext" style={{ marginBottom: 12, color: "var(--text-muted)" }}>
                    💡 What to do: {profitLeaks.discount_leakage.what_to_do}
                  </div>
                  {profitLeaks.discount_leakage.top_products.length > 0 && (
                    <div className="data-table-wrapper">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Product</th>
                            <th className="num">Bills</th>
                            <th className="num">Discount</th>
                          </tr>
                        </thead>
                        <tbody>
                          {profitLeaks.discount_leakage.top_products.map((p) => (
                            <tr key={p.product}>
                              <td>{p.product}</td>
                              <td className="num">{p.lines}</td>
                              <td className="num">{formatInr(p.discount_given)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* 2. Brand Margin Gaps */}
                <div className="summary-card">
                  <h3 style={{ margin: "0 0 6px", fontSize: 15 }}>2. Brand margin gaps</h3>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text-main)", marginBottom: 4 }}>
                    {profitLeaks.brand_margin_gaps.headline}
                  </div>
                  <div className="table-subtext" style={{ marginBottom: 12, color: "var(--text-muted)" }}>
                    💡 What to do: {profitLeaks.brand_margin_gaps.what_to_do}
                  </div>
                  {profitLeaks.brand_margin_gaps.items.length > 0 && (
                    <div className="data-table-wrapper">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Higher-Margin Brand</th>
                            <th>Leader</th>
                            <th className="num">Margin</th>
                            <th className="num">Est. Extra /mo</th>
                          </tr>
                        </thead>
                        <tbody>
                          {profitLeaks.brand_margin_gaps.items.slice(0, 4).map((item) => (
                            <tr key={item.brand}>
                              <td>
                                <div>{item.brand}</div>
                                <div className="table-subtext">{item.product_group}</div>
                              </td>
                              <td>{item.leader}</td>
                              <td className="num">
                                {item.margin_pct}% vs {item.leader_margin_pct}%
                              </td>
                              <td className="num" style={{ color: "var(--profit)", fontWeight: 600 }}>
                                +{formatInr(item.est_extra_profit_per_month)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>

              <div className="grid-two-columns">
                {/* 3. Low-Margin Bestsellers */}
                <div className="summary-card">
                  <h3 style={{ margin: "0 0 6px", fontSize: 15 }}>3. Low-margin bestsellers</h3>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text-main)", marginBottom: 4 }}>
                    {profitLeaks.low_margin_bestsellers.headline}
                  </div>
                  <div className="table-subtext" style={{ marginBottom: 12, color: "var(--text-muted)" }}>
                    💡 What to do: {profitLeaks.low_margin_bestsellers.what_to_do}
                  </div>
                  {profitLeaks.low_margin_bestsellers.items.length > 0 && (
                    <div className="data-table-wrapper">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Product</th>
                            <th className="num">Revenue</th>
                            <th className="num">Margin</th>
                            <th className="num">Below Avg</th>
                          </tr>
                        </thead>
                        <tbody>
                          {profitLeaks.low_margin_bestsellers.items.slice(0, 4).map((p) => (
                            <tr key={p.product}>
                              <td>{p.product}</td>
                              <td className="num">{formatInr(p.revenue)}</td>
                              <td className="num">{p.margin_pct}%</td>
                              <td className="num" style={{ color: "var(--anomaly)" }}>
                                -{p.diff_pct}%
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* 4. Expiry Write-offs */}
                <div className="summary-card">
                  <h3 style={{ margin: "0 0 6px", fontSize: 15 }}>4. Expired stock write-offs</h3>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text-main)", marginBottom: 4 }}>
                    {profitLeaks.expiry_writeoffs.headline}
                  </div>
                  <div className="table-subtext" style={{ marginBottom: 12, color: "var(--text-muted)" }}>
                    💡 What to do: {profitLeaks.expiry_writeoffs.what_to_do}
                  </div>
                  {profitLeaks.expiry_writeoffs.months.length > 0 && (
                    <div className="data-table-wrapper">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Month</th>
                            <th className="num">Write-off Amount</th>
                            <th className="num">% of Revenue</th>
                          </tr>
                        </thead>
                        <tbody>
                          {profitLeaks.expiry_writeoffs.months.slice(0, 4).map((m) => (
                            <tr key={m.month}>
                              <td>{m.month}</td>
                              <td className="num">{formatInr(m.amount)}</td>
                              <td className="num">
                                {m.pct_of_revenue}%
                                {m.is_above_2x_median && (
                                  <span className="badge drop" style={{ marginLeft: 6 }}>
                                    High
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            </section>
          )}

          {/* 9. NEW: Often Bought Together */}
          {basketPairs && (
            <section className="panel">
              <h2>Often bought together</h2>
              <p className="panel-description">
                Market-basket cross-sell analysis. 💡 Tip: Place these next to each other or offer them as a bundle.
              </p>

              {basketPairs.pairs && basketPairs.pairs.length > 0 ? (
                <div className="data-table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Product A</th>
                        <th>Product B</th>
                        <th className="num">Joint Bills</th>
                        <th className="num">Lift</th>
                        <th>Insight</th>
                      </tr>
                    </thead>
                    <tbody>
                      {basketPairs.pairs.map((p, idx) => (
                        <tr key={idx}>
                          <td style={{ fontWeight: 600 }}>{p.group_a}</td>
                          <td style={{ fontWeight: 600 }}>{p.group_b}</td>
                          <td className="num">{p.both_count}</td>
                          <td className="num" style={{ color: "var(--profit)", fontWeight: 700 }}>
                            {p.lift}x
                          </td>
                          <td style={{ color: "#374151" }}>{p.insight}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="empty-notice">No strong product pairs found yet.</p>
              )}
            </section>
          )}
        </>
      )}
    </main>
  );
}
