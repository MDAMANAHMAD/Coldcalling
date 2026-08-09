'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  LayoutDashboard, 
  PhoneCall, 
  Send, 
  Mail, 
  FileText, 
  Ticket, 
  ExternalLink,
  ShieldAlert
} from 'lucide-react';
import { motion } from 'framer-motion';

const NAV_ITEMS = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'AI Cold Calling', href: '/dashboard/cold-calling', icon: PhoneCall },
  { name: 'Messaging Campaign', href: '/sales/campaigns', icon: Send },
  { name: 'Email Classifier', href: '/productivity/emails', icon: Mail },
  { name: 'Invoice Generator', href: '/productivity/invoices', icon: FileText },
  { name: 'Support Tickets', href: '/support/tickets', icon: Ticket },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-dark-card flex flex-col justify-between transition-colors duration-300">
      <div className="flex flex-col flex-1 py-6">
        {/* Logo Section */}
        <div className="px-6 pb-6 border-b border-slate-200 dark:border-slate-800 flex items-center space-x-2">
          <div className="h-9 w-9 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-lg shadow-md shadow-blue-500/30">
            Ω
          </div>
          <div>
            <h1 className="font-bold text-lg leading-none text-slate-800 dark:text-white">Antigravity</h1>
            <span className="text-xs text-slate-400 font-medium">Business Ops Suite</span>
          </div>
        </div>

        {/* Nav Items */}
        <nav className="mt-6 px-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`relative flex items-center space-x-3 px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-200 ${
                  isActive 
                    ? 'text-blue-600 dark:text-blue-400 bg-blue-50/50 dark:bg-blue-950/30' 
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-slate-800/50'
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="activeNavIndicator"
                    className="absolute left-0 top-2 bottom-2 w-1 bg-blue-600 dark:bg-blue-400 rounded-r-md"
                    transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                  />
                )}
                <Icon className={`h-5 w-5 ${isActive ? 'text-blue-600 dark:text-blue-400' : 'text-slate-400 dark:text-slate-500'}`} />
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer / Client Portal Link */}
      <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50">
        <Link
          href="/client-portal"
          target="_blank"
          className="flex items-center justify-between p-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-semibold text-xs shadow-lg hover:shadow-blue-500/20 hover:-translate-y-0.5 transition-all duration-200"
        >
          <div className="flex items-center space-x-2">
            <ExternalLink className="h-4 w-4" />
            <span>Open Client Portal</span>
          </div>
          <span className="px-1.5 py-0.5 rounded bg-white/20 text-[10px] font-bold uppercase tracking-wider">
            Public
          </span>
        </Link>
      </div>
    </aside>
  );
}
