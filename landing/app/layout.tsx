import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GEM — The Intelligence Layer for Creators",
  description:
    "Stop guessing who matters. GEM helps creators find the smartest path to representation, buyers, producers, and capital.",
  openGraph: {
    title: "GEM — The Intelligence Layer for Creators",
    description:
      "Stop guessing who matters. GEM helps creators find the smartest path to representation, buyers, producers, and capital.",
    url: "https://gem.studio",
    siteName: "GEM",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "GEM — The Intelligence Layer for Creators",
    description:
      "Stop guessing who matters. GEM helps creators find the smartest path to representation, buyers, producers, and capital.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
