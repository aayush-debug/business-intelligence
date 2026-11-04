"use client";

import { useEffect, useState, useRef } from "react";
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

// Format integer or float to Indian currency (₹34,87,713)
function formatInr(val) {
  if (val === null || val === undefined || isNaN(val)) return "₹0";
  return "₹" + Math.round(val).toLocaleString("en-IN");
}

// Format axis values with short Indian abbreviations (k, L, Cr)
function formatShortInr(val) {
  if (val === null || val === undefined || isNaN(val)) return "0";
  const abs = Math.abs(val);
  const sign = val < 0 ? "-" : "";
  if (abs >= 1e7) {
    return sign + (abs / 1e7).toFixed(1) + "Cr";
  }
  if (abs >= 1e5) {
    return sign + (abs / 1e5).toFixed(1) + "L";
  }
  if (abs >= 1e3) {
    return sign + (abs / 1e3).toFixed(0) + "k";
  }
  return sign + abs.toString();
}

// Fetch helper with error handling
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
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  // Track active request ID to ignore stale responses when changing date ranges quickly
  const requestIdRef = useRef(0);

  // Fetch forecast once on mount (forecast does not depend on date range selector)
  useEffect(() => {
    let isCurrent = true;
    fetchEndpoint("/api/forecast")
      .then((fc) => {
        if (isCurrent) {
          setForecast(fc);
        }
      })
      .catch((err) => {
        if (isCurrent) {
          setErrorMessage(err.message || "Failed to load forecast data");
        }
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  // Fetch range-dependent datasets whenever `days` changes
  useEffect(() => {
    const currentRequestId = ++requestIdRef.current;
    setLoading(true);
    setErrorMessage("");

    // Granularity: day for 30 days, week for 90 days, month for 1 year and all time
    const granularity = days === 30 ? "day" : days === 90 ? "week" : "month";

    Promise.all([
      fetchEndpoint(`/api/kpis?days=${days}`),
      fetchEndpoint(`/api/trend?granularity=${granularity}&days=${days}`),
      fetchEndpoint(`/api/top-products?days=${days}&limit=8`),
      fetchEndpoint(`/api/top-customers?days=${days}&limit=8`),
      fetchEndpoint(`/api/categories?days=${days}`),
      fetchEndpoint(`/api/anomalies?days=${days}`),
    ])
      .then(([kpis, trend, products, customers, categories, anomalies]) => {
        // Discard stale responses if user clicked another range before this finished
        if (currentRequestId === requestIdRef.current) {
          setData({ kpis, trend, products, customers, categories, anomalies });
          setLoading(false);
        }
      })
      .catch((err) => {
        if (currentRequestId === requestIdRef.current) {
          setErrorMessage(err.message || "Failed to load data");
          setLoading(false);
        }
      });

    return () => {
      // Intentionally not setting state in cleanup, handled by requestIdRef check
    };
  }, [days]);

  return (
    <main className="container">
      {/* 1. Header */}
      <header className="dashboard-header">
        <div className="header-title-group">
          <h1>Business overview</h1>
          <p className="header-subtitle">Performance, profit trends, forecast, and operational anomalies.</p>
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
      </header>

      {/* Error state */}
      {errorMessage && (
        <div className="error-banner" role="alert">
          <strong>Unable to load dashboard data</strong>
          <div>
            Error connecting to <code>{API_BASE}</code>: {errorMessage}. Please verify that the backend server is running and
            <code>NEXT_PUBLIC_API_URL</code> is configured properly.
          </div>
        </div>
      )}

      {/* Loading state message */}
      {loading && !data && <p className="loading-indicator">Loading your numbers…</p>}

      {/* Dashboard Content */}
      {data && (
        <>
          {/* 2. KPI Strip: ONE bordered row with dividers */}
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

          {/* 4. Two Columns: (a) Forecast & (b) Unusual Days */}
          <section className="grid-two-columns">
            {/* Column A: Forecast Chart */}
            <div className="panel">
              <h2>Forecast (next 30 days)</h2>
              {forecast ? (
                <>
                  <p className="panel-description">
                    Total expected revenue is {formatInr(forecast.total_forecast)}. In prior 28-day testing, this projection missed by
                    an average of {formatInr(forecast.backtest.model_mae)} per day, outperforming a same-weekday baseline of{" "}
                    {formatInr(forecast.backtest.naive_mae)} by {forecast.backtest.improvement_pct}%.
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
                        margin={{ top: 10, right: 15, left: 0, bottom: 0 }}
                      >
                        <CartesianGrid stroke="#e6eaef" vertical={false} />
                        <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#5b6b7f" }} minTickGap={40} />
                        <YAxis tickFormatter={formatShortInr} tick={{ fontSize: 11, fill: "#5b6b7f" }} width={54} />
                        <Tooltip
                          formatter={(val) => [formatInr(val)]}
                          contentStyle={{ backgroundColor: "#ffffff", border: "1px solid #d9dfe6", borderRadius: 6, fontSize: 13 }}
                        />
                        <Legend wrapperStyle={{ fontSize: 13, paddingTop: 10 }} />
                        <Line type="monotone" dataKey="actual" name="Actual (last 60 days)" stroke="#3b4cca" strokeWidth={2} dot={false} />
                        <Line
                          type="monotone"
                          dataKey="forecast"
                          name="Forecast (30 days)"
                          stroke="#e29a00"
                          strokeWidth={2}
                          strokeDasharray="5 5"
                          dot={false}
                        />
                        <Line type="monotone" dataKey="lower" name="Lower bound" stroke="#e29a00" strokeWidth={1} strokeOpacity={0.35} dot={false} />
                        <Line type="monotone" dataKey="upper" name="Upper bound" stroke="#e29a00" strokeWidth={1} strokeOpacity={0.35} dot={false} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </>
              ) : (
                <p className="loading-indicator">Loading forecast projection…</p>
              )}
            </div>

            {/* Column B: Unusual Days */}
            <div className="panel">
              <h2>Unusual days</h2>
              <p className="panel-description">Daily sales deviating significantly from typical weekday volume.</p>
              <div style={{ width: "100%", height: 180 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={data.anomalies.series.map((row) => ({
                      ...row,
                      anomalyPoint: row.is_anomaly ? row.revenue : null,
                    }))}
                    margin={{ top: 10, right: 15, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid stroke="#e6eaef" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#5b6b7f" }} minTickGap={45} />
                    <YAxis tickFormatter={formatShortInr} tick={{ fontSize: 11, fill: "#5b6b7f" }} width={54} />
                    <Tooltip
                      formatter={(val) => [formatInr(val)]}
                      contentStyle={{ backgroundColor: "#ffffff", border: "1px solid #d9dfe6", borderRadius: 6, fontSize: 13 }}
                    />
                    <Line type="monotone" dataKey="revenue" name="Daily revenue" stroke="#9aa7b8" strokeWidth={1.5} dot={false} />
                    <Line
                      type="monotone"
                      dataKey="anomalyPoint"
                      name="Unusual day"
                      stroke="none"
                      dot={{ r: 5, fill: "#d64545", stroke: "#d64545" }}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Latest 5 flagged anomalies */}
              <div className="data-table-wrapper" style={{ marginTop: 12 }}>
                {data.anomalies.flagged.length === 0 ? (
                  <p className="empty-notice">No unusual days detected in this time range.</p>
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Type</th>
                        <th className="num">Revenue</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.anomalies.flagged
                        .slice(-5)
                        .reverse()
                        .map((row) => (
                          <tr key={row.date}>
                            <td>{row.date}</td>
                            <td>
                              <span className={`badge ${row.type}`}>{row.type === "spike" ? "Spike" : "Drop"}</span>
                            </td>
                            <td className="num">{formatInr(row.revenue)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </section>

          {/* 5. Two Columns: (a) Top Products & (b) Category Breakdown */}
          <section className="grid-two-columns">
            {/* Column A: Top Products Table */}
            <div className="panel">
              <h2>Top products</h2>
              <p className="panel-description">Highest grossing items sorted by total sales.</p>
              <div className="data-table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th className="num">Revenue</th>
                      <th className="num">Margin</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.products.map((item) => (
                      <tr key={item.product}>
                        <td>
                          <div>{item.product}</div>
                          <div className="table-subtext">{item.category}</div>
                        </td>
                        <td className="num">{formatInr(item.revenue)}</td>
                        <td className="num">{item.margin_pct ? item.margin_pct.toFixed(0) + "%" : "0%"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Column B: Revenue and Profit by Category */}
            <div className="panel">
              <h2>Revenue and profit by category</h2>
              <p className="panel-description">Contribution of each business category to revenue and gross profit.</p>
              <div style={{ width: "100%", height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.categories} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                    <CartesianGrid stroke="#e6eaef" horizontal={false} />
                    <XAxis type="number" tickFormatter={formatShortInr} tick={{ fontSize: 11, fill: "#5b6b7f" }} />
                    <YAxis type="category" dataKey="category" width={130} tick={{ fontSize: 12, fill: "#14213d" }} />
                    <Tooltip
                      formatter={(val) => [formatInr(val)]}
                      contentStyle={{ backgroundColor: "#ffffff", border: "1px solid #d9dfe6", borderRadius: 6, fontSize: 13 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 13, paddingTop: 8 }} />
                    <Bar dataKey="revenue" name="Revenue" fill="#3b4cca" radius={[0, 4, 4, 0]} />
                    <Bar dataKey="profit" name="Gross profit" fill="#0f9d8a" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>

          {/* 6. Top Customers Table */}
          <section className="panel">
            <h2>Top customers</h2>
            <p className="panel-description">Highest spending registered customers (excluding walk-in counter sales).</p>
            <div className="data-table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th className="num">Orders</th>
                    <th className="num">Revenue</th>
                  </tr>
                </thead>
                <tbody>
                  {data.customers.map((cust) => (
                    <tr key={cust.customer}>
                      <td>{cust.customer}</td>
                      <td className="num">{(cust.orders || 0).toLocaleString("en-IN")}</td>
                      <td className="num">{formatInr(cust.revenue)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {/* 7. Empty spot at the bottom for chat panel */}
      <div id="chat-panel-container" className="chat-placeholder" aria-hidden="true" />
    </main>
  );
}

