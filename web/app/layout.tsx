import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FlowLedger — 个人财务管理系统",
  description: "个人资产、支出、投资和预算的统一视图",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
