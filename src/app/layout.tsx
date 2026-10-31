import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import AppLayout from "@/components/AppLayout";
import SarvamNavBar from "@/components/sarvam/SarvamNavBar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Sai Garden — Qualivo Voice Calling Command Center",
  description: "AI Telephony & Lead Acquisition Engine for Sai Garden, Nilje, Dombivli East.",
  icons: {
    icon: "/logo.jpg",
    apple: "/logo.jpg"
  }
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased light" suppressHydrationWarning>
      <body className={`${inter.className} min-h-full bg-slate-50 text-slate-900 flex flex-col`}>
        <AppLayout>
          <SarvamNavBar />
          <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
            {children}
          </main>
        </AppLayout>
      </body>
    </html>
  );
}
