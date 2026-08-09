'use client';

import Sidebar from './Sidebar';
import Header from './Header';
import { usePathname } from 'next/navigation';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isClientPortal = pathname?.startsWith('/client-portal');

  if (isClientPortal) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-dark-bg transition-colors duration-300">
        {children}
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50/70 dark:bg-dark-bg text-slate-900 dark:text-slate-100 transition-colors duration-300">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6 md:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
