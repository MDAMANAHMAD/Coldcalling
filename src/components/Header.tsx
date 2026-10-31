'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { LogOut, PhoneCall } from 'lucide-react';

export default function Header() {
  const router = useRouter();
  const [user, setUser] = useState<{ name: string; email: string; role: string } | null>(null);

  useEffect(() => {
    // Enforce light mode strictly
    document.documentElement.classList.remove('dark');
    document.documentElement.classList.add('light');
    try {
      localStorage.removeItem('theme');
    } catch {}

    try {
      const savedUser = localStorage.getItem('gayatri_user');
      if (savedUser) {
        const parsed = JSON.parse(savedUser);
        setUser(parsed);
      } else {
        setUser({ name: 'Property Advisor', email: 'advisor@saigarden.in', role: 'Sales Team' });
      }
    } catch {
      setUser({ name: 'Property Advisor', email: 'advisor@saigarden.in', role: 'Sales Team' });
    }
  }, []);

  const handleSignOut = () => {
    localStorage.removeItem('gayatri_user');
    router.push('/login');
  };

  return (
    <header className="h-16 px-6 border-b border-slate-200 bg-white/95 backdrop-blur-md flex items-center justify-between sticky top-0 z-30 transition-colors">
      {/* Brand / Title: Strictly Qualivo & Sai Garden */}
      <div className="flex items-center space-x-3 md:space-x-4">
        <Link href="/" className="flex items-center space-x-3 group">
          <div className="h-9 w-9 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-md shadow-blue-500/20 group-hover:scale-105 transition-transform">
            <PhoneCall className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <h1 className="font-extrabold text-sm md:text-base text-slate-900 leading-tight">
                Sai Garden <span className="text-blue-600 font-black">Qualivo Voice</span>
              </h1>
              <span className="hidden sm:inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-700">
                Official Real Estate Suite
              </span>
            </div>
            <p className="text-[10px] text-slate-400 font-medium">
              Lodha Heaven, Nilje, Dombivli East (opp. Xperia Mall)
            </p>
          </div>
        </Link>
      </div>

      {/* Right side: Controls & Profile (Strictly Light Mode, No Dark Mode Toggle) */}
      <div className="flex items-center space-x-3">
        {/* User Info */}
        <div className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-xl bg-blue-500/10 text-blue-600 flex items-center justify-center font-bold text-xs">
            {user?.name ? user.name[0].toUpperCase() : 'S'}
          </div>
          <div className="hidden sm:block text-left">
            <p className="text-xs font-bold text-slate-800 leading-none">
              {user?.name || 'Property Advisor'}
            </p>
            <span className="text-[10px] text-slate-400 font-medium">
              {user?.role || 'Sales Team'}
            </span>
          </div>
        </div>

        <div className="h-6 w-px bg-slate-200" />

        {/* Sign Out Button */}
        <button
          onClick={handleSignOut}
          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl border border-slate-200 hover:border-rose-300 text-slate-600 hover:text-rose-600 hover:bg-rose-50 text-xs font-semibold transition-all"
          title="Sign Out"
        >
          <LogOut className="h-3.5 w-3.5" />
          <span className="hidden md:inline">Sign Out</span>
        </button>
      </div>
    </header>
  );
}
