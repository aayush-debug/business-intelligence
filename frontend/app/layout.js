import "./globals.css";
import Navigation from "./nav";

export const metadata = {
  title: "Company Brain - Business Intelligence & Decision Platform",
  description: "Sales, profit, forecasts, and anomaly detection for small business decisions.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <Navigation />
        {children}
      </body>
    </html>
  );
}
