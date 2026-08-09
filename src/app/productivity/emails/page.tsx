'use client';

import { useState, useEffect } from 'react';
import { 
  getEmails, 
  getEmailRules, 
  saveEmailRules, 
  createEmail, 
  deleteEmail,
  purgeTrashEmails,
  getImapConfig,
  saveImapConfig,
  syncRealEmails
} from '@/app/actions';
import { ClassifiedEmail, EmailFilterRule, ImapConfig } from '@/lib/types';
import { 
  Mail, 
  TrendingUp, 
  Trash2, 
  Settings, 
  Plus, 
  X, 
  ExternalLink, 
  RefreshCw, 
  Inbox, 
  Send,
  Zap,
  Shield,
  Key,
  Database
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function EmailClassifierPage() {
  const [emails, setEmails] = useState<ClassifiedEmail[]>([]);
  const [rules, setRules] = useState<EmailFilterRule[]>([]);
  const [activeTab, setActiveTab] = useState<'All' | 'Urgent' | 'VC' | 'Other' | 'Spam' | 'Trash'>('All');
  const [loading, setLoading] = useState(true);

  // Email simulator state
  const [simSender, setSimSender] = useState('investments@ycombinator.com');
  const [simSubject, setSimSubject] = useState('Antigravity pre-seed pitch follow-up');
  const [simBody, setSimBody] = useState('We loved your demo and would like to extend an offer for our cohort. Let us know if you can sync up on Thursday for a 15-minute onboarding call.');

  // IMAP Settings state
  const [showImapSettings, setShowImapSettings] = useState(false);
  const [imapHost, setImapHost] = useState('imap.gmail.com');
  const [imapPort, setImapPort] = useState(993);
  const [imapUser, setImapUser] = useState('');
  const [imapPass, setImapPass] = useState('');
  const [imapSecure, setImapSecure] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  // Rules edits
  const [editingCategory, setEditingCategory] = useState<string | null>(null);
  const [keywordInput, setKeywordInput] = useState('');
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Fetch initial data
  const fetchData = async () => {
    setLoading(true);
    try {
      const emailList = await getEmails();
      const ruleList = await getEmailRules();
      setEmails(emailList);
      setRules(ruleList);

      const imapSettings = await getImapConfig();
      if (imapSettings) {
        setImapHost(imapSettings.host);
        setImapPort(imapSettings.port);
        setImapUser(imapSettings.user);
        setImapPass(imapSettings.pass);
        setImapSecure(imapSettings.secure);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const triggerToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  // Run email simulation
  const handleSimulateEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!simSender || !simSubject || !simBody) return;

    try {
      const newEmail = await createEmail({
        sender: simSender,
        subject: simSubject,
        body: simBody
      });
      
      // Update local state
      setEmails([newEmail, ...emails]);
      triggerToast(`New Email Received! Classified as: ${newEmail.category}`);
      
      // Reset simulator inputs
      setSimSender('');
      setSimSubject('');
      setSimBody('');
    } catch (e) {
      console.error(e);
    }
  };

  // Save IMAP settings
  const handleSaveImapSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const config: ImapConfig = {
        host: imapHost,
        port: imapPort,
        user: imapUser,
        pass: imapPass,
        secure: imapSecure
      };
      await saveImapConfig(config);
      triggerToast("IMAP Connection settings saved locally!");
      setSyncError(null);
    } catch (e) {
      console.error(e);
      triggerToast("Error saving settings");
    }
  };

  // Sync real IMAP emails
  const handleSyncImap = async () => {
    setSyncing(true);
    setSyncError(null);
    try {
      const result = await syncRealEmails();
      if (result.success) {
        triggerToast(`Sync complete! Loaded ${result.newCount} new emails.`);
        // Refresh email logs
        const emailList = await getEmails();
        setEmails(emailList);
      } else {
        setSyncError(result.error || "An unknown sync error occurred.");
        triggerToast("Email Sync Failed");
      }
    } catch (e: any) {
      setSyncError(e.message || "Connection timeout. Double-check host or password settings.");
      triggerToast("Email Sync Failed");
    } finally {
      setSyncing(false);
    }
  };

  // Delete/Trash email
  const handleDeleteEmail = async (id: string) => {
    try {
      await deleteEmail(id);
      
      // Update local list
      setEmails(emails.map(email => {
        if (email.id === id) {
          if (email.category === 'Trash' || email.category === 'Spam') {
            return null; // permanently removed
          } else {
            return { ...email, category: 'Trash' }; // soft deleted
          }
        }
        return email;
      }).filter(Boolean) as ClassifiedEmail[]);

      triggerToast("Email moved to Trash");
    } catch (e) {
      console.error(e);
    }
  };

  // Soft purge
  const handlePurge = async () => {
    try {
      const count = await purgeTrashEmails();
      setEmails(emails.filter(e => e.category !== 'Trash' && e.category !== 'Spam'));
      triggerToast(`Purged ${count} spam and trash emails successfully!`);
    } catch (e) {
      console.error(e);
    }
  };

  // Start edit rule keyword
  const handleStartEditRule = (rule: EmailFilterRule) => {
    setEditingCategory(rule.category);
    setKeywordInput(rule.keywords.join(', '));
  };

  // Save rule keyword
  const handleSaveRule = async (category: string) => {
    const updatedKeywords = keywordInput.split(',').map(k => k.trim()).filter(Boolean);
    const updatedRules = rules.map(r => r.category === category ? { ...r, keywords: updatedKeywords } : r);
    
    try {
      const savedRules = await saveEmailRules(updatedRules);
      setRules(savedRules);
      setEditingCategory(null);
      triggerToast(`Rules for ${category} updated! Re-evaluating inbox...`);
      
      // Re-fetch email classification updates
      const updatedEmails = await getEmails();
      setEmails(updatedEmails);
    } catch (e) {
      console.error(e);
    }
  };

  // Filtered emails
  const filteredEmails = emails.filter(email => {
    if (activeTab === 'All') return true;
    return email.category === activeTab;
  });

  return (
    <div className="space-y-6">
      
      {/* Toast Alert */}
      <AnimatePresence>
        {toastMessage && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-4 right-4 z-50 px-4 py-3 bg-slate-800 dark:bg-blue-600 text-white rounded-xl shadow-lg flex items-center space-x-2 text-xs font-semibold"
          >
            <Zap className="h-4 w-4 text-amber-400 fill-amber-400" />
            <span>{toastMessage}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* LEFT COLUMN: Classifier Settings & Test Simulator (lg:col-span-4) */}
        <div className="lg:col-span-4 space-y-6">
          
          {/* Real Email Settings Panel */}
          <div className="p-5 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-4">
            <div 
              onClick={() => setShowImapSettings(!showImapSettings)}
              className="flex items-center justify-between cursor-pointer"
            >
              <div className="flex items-center space-x-2">
                <Database className="h-5 w-5 text-blue-500" />
                <h3 className="font-bold text-slate-800 dark:text-white">Real Mail Connection</h3>
              </div>
              <span className="text-xs text-blue-600 dark:text-blue-400 font-semibold hover:underline">
                {showImapSettings ? "Hide Settings" : "Configure IMAP"}
              </span>
            </div>

            <AnimatePresence>
              {showImapSettings && (
                <motion.form 
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  onSubmit={handleSaveImapSettings} 
                  className="space-y-3 border-t border-slate-100 dark:border-slate-850 pt-3"
                >
                  <div className="p-3 bg-blue-50/50 dark:bg-blue-950/10 border border-blue-100/50 dark:border-blue-900/10 rounded-xl space-y-1.5 text-[11px] text-slate-500 leading-normal">
                    <p className="font-bold flex items-center text-blue-600 dark:text-blue-400">
                      <Shield className="h-3.5 w-3.5 mr-1" />
                      Gmail App Password Guide:
                    </p>
                    <ol className="list-decimal pl-4 space-y-1">
                      <li>Go to Google Account &gt; Security</li>
                      <li>Enable 2-Step Verification</li>
                      <li>At the bottom, select <strong>App Passwords</strong></li>
                      <li>Generate a password and copy the 16-character code here</li>
                    </ol>
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">IMAP Host</label>
                    <input
                      type="text"
                      required
                      placeholder="imap.gmail.com"
                      value={imapHost}
                      onChange={(e) => setImapHost(e.target.value)}
                      className="w-full px-3 py-1.5 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs outline-none focus:border-blue-500"
                    />
                  </div>

                  <div className="grid grid-cols-3 gap-2">
                    <div className="col-span-2">
                      <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">IMAP Port</label>
                      <input
                        type="number"
                        required
                        value={imapPort}
                        onChange={(e) => setImapPort(parseInt(e.target.value) || 993)}
                        className="w-full px-3 py-1.5 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs outline-none focus:border-blue-500"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Secure</label>
                      <button
                        type="button"
                        onClick={() => setImapSecure(!imapSecure)}
                        className={`w-full py-1.5 border rounded-lg text-xs font-semibold ${
                          imapSecure 
                            ? 'bg-blue-50 border-blue-200 text-blue-600 dark:bg-blue-950/20 dark:border-blue-900' 
                            : 'border-slate-200 dark:border-slate-700 text-slate-650'
                        }`}
                      >
                        {imapSecure ? "SSL/TLS" : "Plain"}
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Email Username</label>
                    <input
                      type="email"
                      required
                      placeholder="founder@example.com"
                      value={imapUser}
                      onChange={(e) => setImapUser(e.target.value)}
                      className="w-full px-3 py-1.5 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs outline-none focus:border-blue-500"
                    />
                  </div>

                  <div>
                    <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">App Passcode / Password</label>
                    <div className="relative">
                      <input
                        type="password"
                        required
                        placeholder="••••••••••••••••"
                        value={imapPass}
                        onChange={(e) => setImapPass(e.target.value)}
                        className="w-full px-3 py-1.5 pl-8 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs outline-none focus:border-blue-500"
                      />
                      <Key className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
                    </div>
                  </div>

                  <button
                    type="submit"
                    className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow"
                  >
                    Save Connection details
                  </button>
                </motion.form>
              )}
            </AnimatePresence>
          </div>

          {/* Rules Configuration Card */}
          <div className="p-5 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-4">
            <div className="flex items-center space-x-2 pb-3 border-b border-slate-100 dark:border-slate-800">
              <Settings className="h-5 w-5 text-blue-500" />
              <h3 className="font-bold text-slate-800 dark:text-white">Founder Classification Rules</h3>
            </div>
            
            <p className="text-xs text-slate-400 leading-relaxed">
              Define the classification rules. Incoming emails matching these keywords are sorted into folders.
            </p>

            <div className="space-y-3 pt-2">
              {rules.map((rule) => {
                const isEditing = editingCategory === rule.category;
                return (
                  <div key={rule.id} className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 space-y-2">
                    <div className="flex justify-between items-center">
                      <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded tracking-wider uppercase ${
                        rule.category === 'Urgent' 
                          ? 'bg-rose-50 text-rose-600 dark:bg-rose-950/20 dark:text-rose-450'
                          : rule.category === 'VC'
                          ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-950/20 dark:text-indigo-400'
                          : 'bg-amber-50 text-amber-600 dark:bg-amber-950/20 dark:text-amber-400'
                      }`}>
                        {rule.category} Rules
                      </span>
                      
                      {!isEditing ? (
                        <button
                          onClick={() => handleStartEditRule(rule)}
                          className="text-[11px] text-blue-600 dark:text-blue-400 font-semibold hover:underline"
                        >
                          Edit
                        </button>
                      ) : (
                        <div className="flex space-x-2">
                          <button
                            onClick={() => handleSaveRule(rule.category)}
                            className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold hover:underline"
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setEditingCategory(null)}
                            className="text-[11px] text-slate-400 font-semibold hover:underline"
                          >
                            Cancel
                          </button>
                        </div>
                      )}
                    </div>

                    {isEditing ? (
                      <input
                        type="text"
                        value={keywordInput}
                        onChange={(e) => setKeywordInput(e.target.value)}
                        className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 rounded-lg text-xs outline-none focus:border-blue-500"
                        placeholder="Comma separated keywords"
                      />
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {rule.keywords.length === 0 ? (
                          <span className="text-[10px] text-slate-400 italic">No keyword rules defined.</span>
                        ) : (
                          rule.keywords.map(kw => (
                            <span key={kw} className="px-1.5 py-0.5 rounded bg-white dark:bg-slate-800 text-[10px] text-slate-500 dark:text-slate-400 border border-slate-100 dark:border-slate-850">
                              {kw}
                            </span>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Test Email Parser Simulator */}
          <div className="p-5 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-4">
            <div className="flex items-center space-x-2 pb-3 border-b border-slate-100 dark:border-slate-800">
              <Mail className="h-5 w-5 text-indigo-500" />
              <h3 className="font-bold text-slate-800 dark:text-white">Email Parser Simulator</h3>
            </div>
            
            <p className="text-xs text-slate-400 leading-normal">
              Simulate receiving an email. Our rule-engine classifies it and extracts links.
            </p>

            <form onSubmit={handleSimulateEmail} className="space-y-3 pt-2">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Sender Email</label>
                <input
                  type="email"
                  required
                  placeholder="investor@funds.com"
                  value={simSender}
                  onChange={(e) => setSimSender(e.target.value)}
                  className="w-full px-3 py-1.5 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Subject</label>
                <input
                  type="text"
                  required
                  placeholder="Hello founder"
                  value={simSubject}
                  onChange={(e) => setSimSubject(e.target.value)}
                  className="w-full px-3 py-1.5 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Email Body</label>
                <textarea
                  required
                  rows={4}
                  placeholder="Write the email content here..."
                  value={simBody}
                  onChange={(e) => setSimBody(e.target.value)}
                  className="w-full px-3 py-1.5 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs outline-none focus:border-blue-500 resize-none"
                />
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  className="w-full py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-md shadow-indigo-500/20 transition-all flex items-center justify-center space-x-1.5"
                >
                  <Send className="h-3.5 w-3.5" />
                  <span>Receive & Classify Email</span>
                </button>
              </div>
            </form>
          </div>

        </div>

        {/* RIGHT COLUMN: Filter Inbox Dashboard (lg:col-span-8) */}
        <div className="lg:col-span-8 space-y-6">
          
          {/* Connection Error Banner */}
          {syncError && (
            <div className="p-4 bg-rose-50 border border-rose-200 text-rose-600 dark:bg-rose-950/20 dark:border-rose-900 dark:text-rose-400 rounded-2xl text-xs flex items-center space-x-2">
              <span className="font-bold">Sync Error:</span>
              <span>{syncError}</span>
            </div>
          )}

          <div className="bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm overflow-hidden flex flex-col h-full">
            
            {/* Header / Actions */}
            <div className="p-5 border-b border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <h3 className="font-bold text-slate-850 dark:text-white">Daily Classified Inbox</h3>
                <p className="text-xs text-slate-400 mt-1 font-medium">Automatic 7-day soft purge is active for Spam & Trash folders.</p>
              </div>

              <div className="flex space-x-2">
                {/* Real Mail Sync Button */}
                <button
                  onClick={handleSyncImap}
                  disabled={syncing}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl text-xs font-semibold transition-colors flex items-center justify-center space-x-1.5 shadow"
                >
                  {syncing ? (
                    <>
                      <RefreshCw className="h-4.5 w-4.5 animate-spin" />
                      <span>Syncing IMAP...</span>
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-4.5 w-4.5" />
                      <span>Sync Inbox Now</span>
                    </>
                  )}
                </button>

                {/* Soft Purge */}
                <button
                  onClick={handlePurge}
                  className="px-4 py-2 bg-rose-50 hover:bg-rose-100 text-rose-600 dark:bg-rose-950/20 dark:hover:bg-rose-950/40 dark:text-rose-450 border border-rose-100 dark:border-rose-900/30 rounded-xl text-xs font-semibold transition-colors flex items-center justify-center space-x-1.5"
                >
                  <Trash2 className="h-4 w-4" />
                  <span>Soft-Purge</span>
                </button>
              </div>
            </div>

            {/* Filter Tabs */}
            <div className="px-5 bg-slate-50/50 dark:bg-slate-900/20 border-b border-slate-200 dark:border-slate-800 flex overflow-x-auto space-x-1 py-2">
              {(['All', 'Urgent', 'VC', 'Other', 'Spam', 'Trash'] as const).map((tab) => {
                const count = emails.filter(e => tab === 'All' ? true : e.category === tab).length;
                const isSelected = activeTab === tab;
                
                return (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold whitespace-nowrap transition-colors ${
                      isSelected
                        ? 'bg-blue-600 text-white'
                        : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-800 dark:hover:text-white'
                    }`}
                  >
                    {tab} ({count})
                  </button>
                );
              })}
            </div>

            {/* Emails List */}
            <div className="divide-y divide-slate-150 dark:divide-slate-850 max-h-[550px] overflow-y-auto flex-1">
              {loading ? (
                <div className="p-12 text-center text-slate-400 text-sm">
                  Loading classified emails...
                </div>
              ) : filteredEmails.length === 0 ? (
                <div className="p-16 text-center text-slate-400">
                  <div className="flex flex-col items-center space-y-3">
                    <Inbox className="h-10 w-10 text-slate-300" />
                    <p className="text-sm font-semibold">Inbox is completely clean!</p>
                  </div>
                </div>
              ) : (
                filteredEmails.map((email) => (
                  <div key={email.id} className="p-4 flex gap-4 hover:bg-slate-50/30 dark:hover:bg-slate-800/10 transition-colors">
                    
                    {/* Folder classification badge */}
                    <div className="flex-shrink-0 flex flex-col items-center">
                      <span className={`text-[9px] font-extrabold px-2 py-0.5 rounded tracking-wider uppercase select-none ${
                        email.category === 'Urgent'
                          ? 'bg-rose-50 text-rose-600 dark:bg-rose-950/20 dark:text-rose-455'
                          : email.category === 'VC'
                          ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-950/20 dark:text-indigo-400'
                          : email.category === 'Spam'
                          ? 'bg-amber-50 text-amber-600 dark:bg-amber-950/20 dark:text-amber-400'
                          : email.category === 'Trash'
                          ? 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                          : 'bg-blue-50 text-blue-600 dark:bg-blue-950/20 dark:text-blue-400'
                      }`}>
                        {email.category}
                      </span>
                      <span className="text-[10px] text-slate-400 mt-2">
                        {new Date(email.receivedAt).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                      </span>
                    </div>

                    {/* Email Content */}
                    <div className="flex-1 space-y-1">
                      <div className="flex justify-between items-start gap-4">
                        <div>
                          <h4 className="font-bold text-sm text-slate-800 dark:text-white leading-tight">{email.subject}</h4>
                          <span className="text-xs text-slate-400 font-medium">{email.sender}</span>
                        </div>

                        {/* Actionable Direct Links */}
                        {email.actionableLink && (
                          <a
                            href={email.actionableLink}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center space-x-1 text-[11px] text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 font-bold bg-blue-50 dark:bg-blue-950/30 px-2.5 py-1 rounded-lg border border-blue-100/50 dark:border-blue-900/30 hover:scale-102 transition-transform"
                          >
                            <span>Action Link</span>
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                      
                      <p className="text-xs text-slate-500 dark:text-slate-400 whitespace-pre-wrap leading-relaxed pt-1.5">
                        {email.body}
                      </p>
                    </div>

                    {/* Actions (Delete/Permanently delete) */}
                    <div className="flex-shrink-0 flex items-start">
                      <button
                        onClick={() => handleDeleteEmail(email.id)}
                        className="p-1.5 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/20 dark:hover:text-rose-450 rounded-lg text-slate-400 transition-colors"
                        title={email.category === 'Trash' || email.category === 'Spam' ? 'Permanently Delete' : 'Move to Trash'}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>

                  </div>
                ))
              )}
            </div>

          </div>
        </div>

      </div>
    </div>
  );
}
