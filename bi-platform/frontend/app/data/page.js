"use client";

import { useEffect, useState, useRef } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

const DATASETS = [
  {
    key: "products",
    name: "Products",
    description: "Catalog names, categories, costs, retail prices, product groups, and manufacturers.",
    order: 1,
  },
  {
    key: "sales",
    name: "Sales",
    description: "Invoices, transaction dates, product IDs, quantities, and totals. Customer names are optional.",
    order: 2,
  },
  {
    key: "inventory",
    name: "Inventory",
    description: "Current stock on hand, reorder thresholds, batch numbers, and expiry dates.",
    order: 3,
  },
  {
    key: "expenses",
    name: "Expenses",
    description: "Monthly operating costs, rent, utilities, and expired stock write-offs.",
    order: 4,
  },
];

export default function YourDataPage() {
  const [dataStatus, setDataStatus] = useState(null);
  const [selectedDataset, setSelectedDataset] = useState(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [mapping, setMapping] = useState({});
  const [mode, setMode] = useState("append");
  const [importing, setImporting] = useState(false);
  const [commitResult, setCommitResult] = useState(null);
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const fileInputRef = useRef(null);

  const handleLoadDemoData = async () => {
    setLoadingDemo(true);
    setErrorMessage("");
    try {
      const res = await fetch(`${API_BASE}/api/demo/load`, { method: "POST" });
      const resData = await res.json();
      if (!res.ok) {
        throw new Error(resData.detail || "Failed to load demo data");
      }
      fetchStatus();
      alert("Sample test data loaded successfully! You can now view the Dashboard.");
    } catch (err) {
      setErrorMessage(err.message || "Failed to load demo data.");
    } finally {
      setLoadingDemo(false);
    }
  };

  const fetchStatus = () => {
    fetch(`${API_BASE}/api/data/status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setDataStatus(data);
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleCardClick = (ds) => {
    setSelectedDataset(ds);
    setFile(null);
    setPreview(null);
    setMapping({});
    setCommitResult(null);
    setErrorMessage("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleFileChange = async (e) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;
    setFile(selectedFile);
    setPreview(null);
    setCommitResult(null);
    setErrorMessage("");

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("dataset", selectedDataset.key);

    try {
      const res = await fetch(`${API_BASE}/api/import/preview`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to preview file");
      }
      setPreview(data);
      setMapping(data.suggested_mapping || {});
    } catch (err) {
      setErrorMessage(err.message || "Failed to parse file.");
    }
  };

  const handleMappingChange = (targetField, sourceCol) => {
    setMapping((prev) => ({
      ...prev,
      [targetField]: sourceCol || null,
    }));
  };

  const handleCommit = async () => {
    if (!file || !selectedDataset) return;

    if (mode === "replace") {
      const ok = window.confirm(
        `Are you sure you want to REPLACE all existing ${selectedDataset.name}? Existing rows in this dataset will be deleted permanently.`
      );
      if (!ok) return;
    }

    setImporting(true);
    setErrorMessage("");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("dataset", selectedDataset.key);
    formData.append("mapping", JSON.stringify(mapping));
    formData.append("mode", mode);

    try {
      const res = await fetch(`${API_BASE}/api/import/commit`, {
        method: "POST",
        body: formData,
      });
      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || "Import commit failed.");
      }
      setCommitResult(result);
      fetchStatus();
    } catch (err) {
      setErrorMessage(err.message || "Failed to import data.");
    } finally {
      setImporting(false);
    }
  };

  const isMockLoaded = Boolean(dataStatus?.sales?.loaded && dataStatus?.products?.rows === 54);

  return (
    <main className="container">
      <header className="dashboard-header">
        <div className="header-title-group">
          <h1>Your data</h1>
          <p className="header-subtitle">
            Upload CSV, TSV, TXT, Excel, or JSON files.
            <span style={{ marginLeft: 8, fontWeight: 600, color: "var(--revenue)" }}>
              Recommended order: Products → Sales → Inventory → Expenses.
            </span>
          </p>
        </div>
      </header>

      {/* Mock Data Banner */}
      <div
        style={{
          background: isMockLoaded ? "#eff6ff" : "#f0f4f8",
          border: isMockLoaded ? "1px solid #bfdbfe" : "1px solid var(--border-color)",
          padding: "14px 18px",
          borderRadius: 8,
          marginBottom: 20,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div>
          <div
            style={{
              fontWeight: 700,
              fontSize: 14,
              color: isMockLoaded ? "#1e40af" : "var(--text-main)",
            }}
          >
            {isMockLoaded
              ? "🧪 Currently loaded: Mock pharmacy data"
              : "Looking to test the platform with mock data?"}
          </div>
          <div
            style={{
              fontSize: 13,
              color: isMockLoaded ? "#2563eb" : "var(--text-muted)",
              marginTop: 3,
            }}
          >
            {isMockLoaded
              ? "The platform is populated with pre-configured mock pharmacy data (54 products, 420 customers, 94,676 sales, 188 expenses, 53 inventory batches). You can replace any dataset below with your own real business files."
              : "Load the pre-configured mock pharmacy dataset (54 products, stock on hand, 2 years of sales, and expenses) to explore the system."}
          </div>
        </div>

        {isMockLoaded ? (
          <span
            className="badge ok"
            style={{
              backgroundColor: "#dbeafe",
              color: "#1e40af",
              padding: "6px 12px",
              fontSize: 12.5,
              fontWeight: 600,
            }}
          >
            Mock data active
          </span>
        ) : (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleLoadDemoData}
            disabled={loadingDemo}
          >
            {loadingDemo ? "Loading mock data…" : "🧪 Load mock test data"}
          </button>
        )}
      </div>

      {/* 5 Dataset Cards */}
      <section className="summary-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))" }}>
        {DATASETS.map((ds) => {
          const st = dataStatus ? dataStatus[ds.key] : null;
          const rows = st ? st.rows : 0;
          const isSelected = selectedDataset?.key === ds.key;

          return (
            <div
              key={ds.key}
              className="summary-card"
              style={{
                cursor: "pointer",
                borderColor: isSelected ? "var(--revenue)" : "var(--border-color)",
                boxShadow: isSelected ? "0 0 0 2px var(--revenue)" : "none",
                transition: "all 0.15s ease",
              }}
              onClick={() => handleCardClick(ds)}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <span className="summary-card-title">Step {ds.order}</span>
                <span className={`badge ${rows > 0 ? "ok" : "drop"}`}>
                  {rows > 0 ? `${rows.toLocaleString("en-IN")} Rows${isMockLoaded ? " (Mock)" : ""}` : "Empty"}
                </span>
              </div>
              <h3 style={{ margin: "8px 0 4px", fontSize: 17 }}>{ds.name}</h3>
              <p style={{ fontSize: 12.5, color: "var(--text-muted)", margin: "0 0 12px", minHeight: 36 }}>
                {ds.description}
              </p>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <a
                  href={`${API_BASE}/api/import/template/${ds.key}`}
                  download={`${ds.key}_template.csv`}
                  className="btn btn-secondary btn-sm"
                  onClick={(e) => e.stopPropagation()}
                >
                  Download template
                </a>
                <span style={{ fontSize: 12.5, color: "var(--revenue)", fontWeight: 600 }}>
                  {isSelected ? "Active" : "Upload →"}
                </span>
              </div>
            </div>
          );
        })}
      </section>

      {/* Upload & Mapping Section */}
      {selectedDataset && (
        <section className="panel" style={{ marginTop: 24 }}>
          <h2>Upload {selectedDataset.name}</h2>
          <p className="panel-description">
            Choose a file (.csv, .tsv, .txt, .xlsx, .json) up to 20MB. Check column mappings below before importing.
          </p>

          {errorMessage && (
            <div className="error-banner" style={{ margin: "16px 0" }}>
              <strong>Error:</strong> {errorMessage}
            </div>
          )}

          <div style={{ display: "flex", gap: 16, alignItems: "center", marginBottom: 20, flexWrap: "wrap" }}>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.tsv,.txt,.xlsx,.json"
              onChange={handleFileChange}
              style={{ fontSize: 14 }}
            />
            {preview && (
              <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
                Detected <strong>{preview.row_count}</strong> rows across <strong>{preview.columns?.length}</strong> columns.
              </span>
            )}
          </div>

          {/* Preview & Mapping Table */}
          {preview && !commitResult && (
            <div>
              <h3 style={{ fontSize: 15, margin: "20px 0 8px" }}>1. Confirm Column Mapping</h3>
              <p className="panel-description">Match your file's columns with the expected system fields (* = required).</p>

              <div className="data-table-wrapper" style={{ marginBottom: 24 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Target Field</th>
                      <th>Mapped Source Column in File</th>
                      <th>Sample Data (Row 1)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.keys(preview.suggested_mapping || {}).map((targetField) => {
                      const isRequired = preview.missing_required?.includes(targetField) ||
                        ["name", "category", "unit_cost", "unit_price", "invoice_id", "sale_date", "quantity", "total_amount", "amount", "stock_on_hand"].includes(targetField);
                      const currentVal = mapping[targetField] || "";
                      const sampleVal = preview.sample_rows?.[0]?.[currentVal] ?? "—";

                      return (
                        <tr key={targetField}>
                          <td style={{ fontWeight: 600 }}>
                            {targetField} {isRequired && <span style={{ color: "var(--anomaly)" }}>*</span>}
                          </td>
                          <td>
                            <select
                              className="form-select"
                              value={currentVal}
                              onChange={(e) => handleMappingChange(targetField, e.target.value)}
                              style={{ maxWidth: 260 }}
                            >
                              <option value="">(Select column or skip)</option>
                              {preview.columns.map((col) => (
                                <option key={col} value={col}>
                                  {col}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td style={{ color: "var(--text-muted)", fontSize: 13 }}>{String(sampleVal)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Sample Data Preview Table */}
              <h3 style={{ fontSize: 15, margin: "20px 0 8px" }}>2. Sample Data (First 5 Rows)</h3>
              <div className="data-table-wrapper" style={{ marginBottom: 24, maxHeight: 220, overflowY: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      {preview.columns.map((col) => (
                        <th key={col}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sample_rows.map((r, idx) => (
                      <tr key={idx}>
                        {preview.columns.map((col) => (
                          <td key={col} style={{ fontSize: 13 }}>
                            {r[col] !== null && r[col] !== undefined ? String(r[col]) : ""}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Import Options & Action */}
              <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap", borderTop: "1px solid var(--border-light)", paddingTop: 16 }}>
                <div>
                  <label style={{ fontSize: 13.5, fontWeight: 600, marginRight: 10 }}>Import Mode:</label>
                  <label style={{ marginRight: 14, fontSize: 13.5 }}>
                    <input
                      type="radio"
                      name="mode"
                      value="append"
                      checked={mode === "append"}
                      onChange={(e) => setMode(e.target.value)}
                      style={{ marginRight: 4 }}
                    />
                    Append new rows
                  </label>
                  <label style={{ fontSize: 13.5 }}>
                    <input
                      type="radio"
                      name="mode"
                      value="replace"
                      checked={mode === "replace"}
                      onChange={(e) => setMode(e.target.value)}
                      style={{ marginRight: 4 }}
                    />
                    Replace existing data
                  </label>
                </div>

                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleCommit}
                  disabled={importing}
                >
                  {importing ? "Importing…" : `Import ${selectedDataset.name}`}
                </button>
              </div>
            </div>
          )}

          {/* Import Result Summary */}
          {commitResult && (
            <div style={{ background: "#f8fafc", padding: 20, borderRadius: 8, marginTop: 16, border: "1px solid var(--border-color)" }}>
              <h3 style={{ margin: "0 0 10px", color: "var(--success-text)", fontSize: 16 }}>
                🎉 Import Completed
              </h3>
              <ul style={{ margin: "0 0 16px", paddingLeft: 20, fontSize: 14 }}>
                <li>
                  Successfully inserted: <strong>{commitResult.inserted.toLocaleString("en-IN")}</strong> rows
                </li>
                <li>
                  Skipped duplicates: <strong>{commitResult.skipped_duplicates.toLocaleString("en-IN")}</strong> rows
                </li>
                <li>
                  Rejected invalid rows:{" "}
                  <strong style={{ color: commitResult.rejected?.length ? "var(--anomaly)" : "inherit" }}>
                    {commitResult.rejected?.length || 0}
                  </strong>{" "}
                  rows
                </li>
              </ul>

              {commitResult.rejected_csv_url && (
                <div style={{ marginTop: 12 }}>
                  <a
                    href={`${API_BASE}${commitResult.rejected_csv_url}`}
                    download="rejected_rows.csv"
                    className="btn btn-danger btn-sm"
                  >
                    Download rejected rows (with reasons)
                  </a>
                </div>
              )}

              <div style={{ marginTop: 16 }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    setPreview(null);
                    setCommitResult(null);
                    setFile(null);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                >
                  Upload another file
                </button>
              </div>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
