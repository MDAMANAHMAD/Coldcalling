'use client';

import { useEffect, useState } from 'react';
import Header from './Header';
import { usePathname, useRouter } from 'next/navigation';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isLoginPage = pathname === '/login';
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    // Enforce light mode strictly
    document.documentElement.classList.remove('dark');
    document.documentElement.classList.add('light');
    try {
      localStorage.removeItem('theme');
    } catch {}

    const user = localStorage.getItem('gayatri_user');
    if (!user && pathname !== '/login') {
      router.push('/login');
    }
  }, [pathname, router]);

  if (isLoginPage) {
    return (
      <div className="min-h-screen bg-slate-50 text-slate-900">
        {children}
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      <Header />
      <div className="flex-1 w-full">
        {children}
      </div>
    </div>
  );
}
