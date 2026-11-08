import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Blast Radius Zero — Execution Control",
  description: "Real agentic work. Visible containment. Run Python and browser tasks inside isolated Vultr sandboxes.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
