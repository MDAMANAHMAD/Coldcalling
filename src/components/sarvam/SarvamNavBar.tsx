'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Home, BarChart3, CalendarCheck, HeartHandshake, PhoneCall } from 'lucide-react';

export default function SarvamNavBar() {
  const pathname = usePathname();

  // Do not render navigation bar on login page
  if (pathname === '/login') return null;

  const navItems = [
    { href: '/', label: 'Home & Upload', icon: Home, exact: true },
    { href: '/analytics', label: 'Analytics', icon: BarChart3 },
    { href: '/site-visits', label: 'Site Visits', icon: CalendarCheck },
    { href: '/interested', label: 'Interested Leads', icon: HeartHandshake },
    { href: '/call-logs', label: 'All Call Logs', icon: PhoneCall }
  ];

  return (
    <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-b border-slate-200 dark:border-slate-800 sticky top-16 z-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-3">
          {/* Project Title & Badge */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg overflow-hidden border border-slate-200 bg-slate-950 flex-shrink-0">
                <img src="/logo.jpg" alt="Qualivo" className="w-full h-full object-cover" />
              </div>
              <h2 className="text-base font-extrabold text-slate-900">
                Sai Garden <span className="text-blue-600">Qualivo Voice</span>
              </h2>
            </div>
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-purple-100 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300 border border-purple-200 dark:border-purple-800">
              Agent: Gayatri (Nilje, Dombivli East)
            </span>
          </div>

          {/* Navigation Pills */}
          <nav className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
            {navItems.map(item => {
              const Icon = item.icon;
              const isActive = item.exact
                ? pathname === item.href
                : pathname.startsWith(item.href);

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
                    isActive
                      ? 'bg-blue-600 text-white shadow-sm shadow-blue-500/25'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800/80'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </div>
    </div>
  );
}
