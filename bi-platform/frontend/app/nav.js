"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export default function Navigation() {
  const pathname = usePathname();
  const [dayStatus, setDayStatus] = useState(null);
  const [config, setConfig] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/config`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setConfig(data);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/api/day/status`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setDayStatus(data);
      })
      .catch(() => {});
  }, [pathname]);

  const lastClosed = dayStatus?.last_closed_date;
  const openDays = dayStatus?.open_days || [];
  const openCount = openDays.length;
  const isSnapshot = Boolean(config?.snapshot_mode);
  const snapshotDateStr = config?.snapshot_built_at
    ? new Date(config.snapshot_built_at).toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "";

  const links = [
    { href: "/", label: "Dashboard" },
    { href: "/chat", label: "Ask AI" },
    { href: "/data", label: "Your data" },
    { href: "/billing", label: "Billing" },
    { href: "/reorder", label: "Reorder" },
    { href: "/summary", label: "Daily summaries" },
  ];

  return (
    <>
      <nav className="top-nav">
        <div className="nav-container">
          <div className="nav-left">
            <Link href="/" className="nav-brand">
              <span>🧠 Company Brain</span>
            </Link>
            <div className="nav-links">
              {links.map((link) => {
                const isActive = pathname === link.href;
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`nav-link ${isActive ? "active" : ""}`}
                  >
                    {link.label}
                  </Link>
                );
              })}
            </div>
          </div>
          <div className="nav-right" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {(isSnapshot || config?.demo_mode || dayStatus?.is_mock_data) && (
              <span
                style={{
                  background: "#fef3c7",
                  color: "#b45309",
                  border: "1px solid #fde68a",
                  borderRadius: "6px",
                  padding: "2px 8px",
                  fontSize: "12px",
                  fontWeight: 600,
                }}
              >
                Demo data
              </span>
            )}
            {lastClosed ? (
              <span className="nav-status-badge">
                Data up to {new Date(lastClosed + "T00:00:00").toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                  year: "numeric"
                })}
              </span>
            ) : (
              <span className="nav-status-badge">No closed days</span>
            )}
          </div>
        </div>
      </nav>

      {isSnapshot && snapshotDateStr && (
        <div
          style={{
            background: "#eff6ff",
            color: "#1d4ed8",
            borderBottom: "1px solid #dbeafe",
            padding: "6px 20px",
            fontSize: "13px",
            textAlign: "center",
            fontWeight: 500,
          }}
        >
          Sample data snapshot built {snapshotDateStr}
        </div>
      )}

      {openCount > 0 && !isSnapshot && (
        <div className="banner-warning">
          <span>
            {openCount} day{openCount > 1 ? "s" : ""} not closed yet.
            <Link href="/billing">Close the day to see today's numbers.</Link>
          </span>
        </div>
      )}
    </>
  );
}
