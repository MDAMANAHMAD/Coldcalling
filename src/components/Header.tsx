'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Sun, Moon, LogOut, User, PhoneCall } from 'lucide-react';

export default function Header() {
  const router = useRouter();
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [user, setUser] = useState<{ name: string; email: string; role: string } | null>(null);

  useEffect(() => {
    // Load theme preference
    const savedTheme = localStorage.getItem('theme');
    const isDark = savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches);
    if (isDark) {
      document.documentElement.classList.add('dark');
      setTheme('dark');
    } else {
      document.documentElement.classList.remove('dark');
      setTheme('light');
    }

    // Load active user
    try {
      const savedUser = localStorage.getItem('gayatri_user');
      if (savedUser) {
        const parsed = JSON.parse(savedUser);
        if (parsed.email === 'tony@starkindustries.com') {
          parsed.name = 'Test User';
          parsed.email = 'test@gmail.com';
          localStorage.setItem('gayatri_user', JSON.stringify(parsed));
        }
        setUser(parsed);
      } else {
        setUser({ name: 'Test User', email: 'test@gmail.com', role: 'Property Advisor' });
      }
    } catch {
      setUser({ name: 'Test User', email: 'test@gmail.com', role: 'Property Advisor' });
    }
  }, []);

  const toggleTheme = () => {
    if (theme === 'light') {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
      setTheme('dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
      setTheme('light');
    }
  };

  const handleSignOut = () => {
    localStorage.removeItem('gayatri_user');
    router.push('/login');
  };

  return (
    <header className="h-16 px-6 border-b border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md flex items-center justify-between sticky top-0 z-30 transition-colors">
      {/* Brand / Title & Switcher */}
      <div className="flex items-center space-x-3 md:space-x-4">
        <Link href="/sarvam-dashboard" className="flex items-center space-x-3 group">
          <div className="h-9 w-9 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-md shadow-blue-500/20 group-hover:scale-105 transition-transform">
            <PhoneCall className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <h1 className="font-extrabold text-sm md:text-base text-slate-900 dark:text-white leading-tight">
                Sai Garden <span className="text-blue-600 font-black">Voice AI</span>
              </h1>
              <span className="hidden sm:inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-100 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300">
                Sarvam Powered
              </span>
            </div>
            <p className="text-[10px] text-slate-400 font-medium">
              Lodha Heaven, Nilje, Dombivli East (opp. Xperia Mall)
            </p>
          </div>
        </Link>

        {/* Dashboard Switcher Tabs */}
        <div className="hidden lg:flex items-center gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-xl text-xs font-semibold">
          <Link
            href="/sarvam-dashboard"
            className="px-2.5 py-1 rounded-lg text-blue-600 dark:text-blue-400 bg-white dark:bg-slate-700 shadow-xs"
          >
            Sarvam Dashboard
          </Link>
          <Link
            href="/"
            className="px-2.5 py-1 rounded-lg text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors"
          >
            Classic LiveKit
          </Link>
        </div>
      </div>

      {/* Right side: Controls & Profile */}
      <div className="flex items-center space-x-3">
        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-xl text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
        >
          {theme === 'light' ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
        </button>

        <div className="h-6 w-px bg-slate-200 dark:bg-slate-800" />

        {/* User Info */}
        <div className="flex items-center space-x-2.5">
          <div className="h-8 w-8 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold text-xs">
            {user?.name ? user.name[0].toUpperCase() : 'G'}
          </div>
          <div className="hidden sm:block text-left">
            <p className="text-xs font-bold text-slate-800 dark:text-slate-200 leading-none">
              {user?.name || 'Property Advisor'}
            </p>
            <span className="text-[10px] text-slate-400 font-medium">
              {user?.role || 'Advisor'}
            </span>
          </div>
        </div>

        {/* Sign Out Button */}
        <button
          onClick={handleSignOut}
          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-rose-300 dark:hover:border-rose-900 text-slate-600 dark:text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 hover:bg-rose-50/50 dark:hover:bg-rose-950/20 text-xs font-semibold transition-all"
          title="Sign Out"
        >
          <LogOut className="h-3.5 w-3.5" />
          <span className="hidden md:inline">Sign Out</span>
        </button>
      </div>
    </header>
  );
}
