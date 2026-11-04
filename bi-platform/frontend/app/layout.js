import "./globals.css";

export const metadata = {
  title: "Business overview",
  description: "Sales, profit, forecasts, and anomaly detection for small business decisions.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
