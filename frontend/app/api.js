// Centralized API configuration for Company Brain

function getInitialApiBase() {
  if (typeof window !== "undefined") {
    const custom = localStorage.getItem("company_brain_api_url");
    if (custom && custom.trim()) {
      return custom.trim().replace(/\/+$/, "");
    }
  }
  return (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
}

export const API_BASE = getInitialApiBase();

export function setCustomApiBase(url) {
  if (typeof window !== "undefined") {
    if (!url || !url.trim()) {
      localStorage.removeItem("company_brain_api_url");
    } else {
      let cleanUrl = url.trim().replace(/\/+$/, "");
      if (!cleanUrl.startsWith("http://") && !cleanUrl.startsWith("https://")) {
        cleanUrl = "https://" + cleanUrl;
      }
      localStorage.setItem("company_brain_api_url", cleanUrl);
    }
    window.location.reload();
  }
}

export function getCustomApiBase() {
  if (typeof window !== "undefined") {
    return localStorage.getItem("company_brain_api_url") || "";
  }
  return "";
}
