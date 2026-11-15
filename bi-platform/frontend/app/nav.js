"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export default function Navigation() {
  const pathname = usePathname();
  const [dayStatus, setDayStatus] = useState(null);

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
          <div className="nav-right">
            {lastClosed ? (
              <span className="nav-status-badge">
                Data up to {new Date(lastClosed + "T00:00:00").toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                  year: "numeric"
                })}
                {lastClosed === "2026-10-31" ? " (Mock data)" : ""}
              </span>
            ) : (
              <span className="nav-status-badge">No closed days</span>
            )}
          </div>
        </div>
      </nav>

      {openCount > 0 && (
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
