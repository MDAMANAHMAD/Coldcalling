import SarvamNavBar from '@/components/sarvam/SarvamNavBar';

export const metadata = {
  title: 'Sai Garden — Sarvam AI Voice Calling Dashboard',
  description: 'AI Telephony & Lead Intelligence for Sai Garden Dombivli East (Powered by Sarvam AI)'
};

export default function SarvamDashboardLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex flex-col">
      <SarvamNavBar />
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {children}
      </main>
    </div>
  );
}
