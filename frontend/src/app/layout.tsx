import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Meeting memory assistant",
  description: "Transcripts with speakers, summaries, action items and decisions for your meetings.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <nav className="border-b border-slate-200 dark:border-slate-800">
          <div className="mx-auto max-w-5xl px-4 py-3">
            <Link href="/" className="font-semibold">
              Meeting memory
            </Link>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
