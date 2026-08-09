'use client';

import { useState, useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { Sun, Moon, Bell, User } from 'lucide-react';

export default function Header() {
  const pathname = usePathname();
  const [theme, setTheme] = useState<'light' | 'dark'>('light');

  // Load theme preference on mount
  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    const isDark = savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches);
    
    if (isDark) {
      document.documentElement.classList.add('dark');
      setTheme('dark');
    } else {
      document.documentElement.classList.remove('dark');
      setTheme('light');
    }
  }, []);

  // Toggle theme
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

  // Get display title based on path
  const getTitle = () => {
    switch (pathname) {
      case '/': return 'Dashboard Overview';
      case '/sales/crm': return 'Sales CRM & Pipeline';
      case '/sales/campaigns': return 'Outbound Messaging Campaigns';
      case '/productivity/emails': return 'AI Email Classifier & Purge';
      case '/productivity/invoices': return 'Dynamic Invoice Generator';
      case '/support/tickets': return 'Customer Helpdesk & Ticket Console';
      case '/client-portal': return 'Customer Help Center';
      default: return 'Antigravity Suite';
    }
  };

  return (
    <header className="h-16 px-6 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-dark-card flex items-center justify-between transition-colors duration-300">
      <div>
        <h2 className="font-bold text-xl text-slate-800 dark:text-white leading-tight">
          {getTitle()}
        </h2>
      </div>

      <div className="flex items-center space-x-4">
        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
        >
          {theme === 'light' ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
        </button>

        {/* Notifications Mock */}
        <div className="relative">
          <button className="p-2 rounded-lg text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
            <Bell className="h-5 w-5" />
            <span className="absolute top-1 right-1 h-2.5 w-2.5 rounded-full bg-rose-500 ring-2 ring-white dark:ring-dark-card" />
          </button>
        </div>

        <div className="h-8 w-px bg-slate-200 dark:bg-slate-800" />

        {/* User profile */}
        <div className="flex items-center space-x-2">
          <div className="h-8 w-8 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold text-sm">
            F
          </div>
          <div className="hidden md:block text-left">
            <p className="text-xs font-semibold text-slate-700 dark:text-slate-200 leading-none">Tony Stark</p>
            <span className="text-[10px] text-slate-400 font-medium">Founder Profile</span>
          </div>
        </div>
      </div>
    </header>
  );
}
