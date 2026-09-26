import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import AppLayout from "@/components/AppLayout";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Gayatri AI — Cold Calling",
  description: "Gayatri AI Voice Agent for real estate cold calling. Dials customers, pitches Sai Complex Dombivli East, handles objections in Hindi, Marathi and English, and books site visits automatically.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <body className={`${inter.className} h-full bg-slate-50 dark:bg-dark-bg text-slate-900 dark:text-slate-100 transition-colors duration-300`}>
        <AppLayout>{children}</AppLayout>
      </body>
    </html>
  );
}
