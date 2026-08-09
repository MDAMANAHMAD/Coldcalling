'use client';

import { useState } from 'react';
import { getTicketById, createTicket } from '@/app/actions';
import { Ticket, TicketMessage } from '@/lib/types';
import { 
  MessageSquare, 
  Search, 
  HelpCircle, 
  ChevronDown, 
  ChevronUp, 
  Send, 
  FileText, 
  CheckCircle2, 
  Clock, 
  AlertCircle,
  ArrowRight,
  Sparkles,
  User,
  ShieldCheck,
  X
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const FAQ_ITEMS = [
  {
    q: "How do I reset my account password?",
    a: "You can reset your password by going to the login page, clicking 'Forgot Password', and entering your registered email address. We will send you a reset link instantly."
  },
  {
    q: "Why is the invoice downloader exporting a blank page?",
    a: "This is usually caused by outdated browser caches blocking font loading. Try clearing your cookies/cache, or try using Chrome/Firefox to export the invoice. If it persists, raise a ticket below."
  },
  {
    q: "How long does the AI Email Classifier keep Trash emails?",
    a: "The classifier holds emails in the Spam and Trash folder for 7 days. You can trigger a manual soft-purge anytime in the email classifier settings dashboard."
  },
  {
    q: "Where can I configure custom Objection Handler rules?",
    a: "Objection rules can be added in the 'Outbound Messaging Campaigns' tab in your founder dashboard. Specify keywords and the response text, and the simulator will instantly pick them up."
  }
];

export default function ClientPortalPage() {
  // FAQ accordion state
  const [openFaqIdx, setOpenFaqIdx] = useState<number | null>(null);

  // Status tracker state
  const [searchTicketId, setSearchTicketId] = useState('');
  const [trackedTicket, setTrackedTicket] = useState<Ticket | null>(null);
  const [trackError, setTrackError] = useState<string | null>(null);
  const [isTracking, setIsTracking] = useState(false);

  // Chatbot state
  const [chatMessages, setChatMessages] = useState<TicketMessage[]>([
    { sender: 'bot', message: 'Hello! I am your virtual assistant. How can I help you today? You can select a question from the FAQ or type below.', timestamp: new Date().toISOString() }
  ]);
  const [userInput, setUserInput] = useState('');
  const [isBotTyping, setIsBotTyping] = useState(false);
  const [unresolvedCount, setUnresolvedCount] = useState(0);
  const [showEscalateButton, setShowEscalateButton] = useState(false);

  // Escalation Modal
  const [isTicketModalOpen, setIsTicketModalOpen] = useState(false);
  const [customerName, setCustomerName] = useState('');
  const [customerEmail, setCustomerEmail] = useState('');
  const [issueDescription, setIssueDescription] = useState('');
  const [createdTicketId, setCreatedTicketId] = useState<string | null>(null);

  // FAQ Accordion Toggle
  const toggleFaq = (idx: number) => {
    setOpenFaqIdx(openFaqIdx === idx ? null : idx);
  };

  // Ticket status lookup
  const handleTrackTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchTicketId) return;
    
    setIsTracking(true);
    setTrackError(null);
    setTrackedTicket(null);

    try {
      let formattedId = searchTicketId.trim();
      if (!formattedId.startsWith('#')) {
        formattedId = `#${formattedId}`;
      }
      
      const ticket = await getTicketById(formattedId);
      if (ticket) {
        setTrackedTicket(ticket);
      } else {
        setTrackError(`No ticket found with ID ${searchTicketId}. Check spelling and format (e.g. TCK-1001).`);
      }
    } catch (e) {
      setTrackError("Error looking up ticket. Please try again.");
    } finally {
      setIsTracking(false);
    }
  };

  // Bot response logic
  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!userInput.trim()) return;

    const userMsg: TicketMessage = {
      sender: 'user',
      message: userInput,
      timestamp: new Date().toISOString()
    };

    setChatMessages(prev => [...prev, userMsg]);
    setUserInput('');
    setIsBotTyping(true);
    setUnresolvedCount(prev => prev + 1);

    setTimeout(() => {
      let botResponse = "I am sorry, I did not quite catch that. Could you try rephrasing or check our FAQs? Alternatively, feel free to escalate to a human agent using the button below.";
      const msg = userMsg.message.toLowerCase();

      if (msg.includes('hello') || msg.includes('hi') || msg.includes('hey')) {
        botResponse = "Hello there! What support topic can I assist you with today?";
      } else if (msg.includes('password') || msg.includes('login') || msg.includes('reset')) {
        botResponse = "For login issues: Click 'Forgot Password' on the login screen. If you get a 500 error, our team may be running server updates. Please wait 10 minutes and try again.";
      } else if (msg.includes('invoice') || msg.includes('pdf') || msg.includes('blank') || msg.includes('download')) {
        botResponse = "If your exported invoice is blank, it's typically a canvas rendering cache issue. Try running in Incognito mode, clear cookies, or use another browser to download the PDF.";
      } else if (msg.includes('campaign') || msg.includes('objection') || msg.includes('reply')) {
        botResponse = "You can add and manage custom objection keywords directly under 'Outbound Messaging Campaigns' in your admin panel.";
      } else if (msg.includes('email') || msg.includes('classify') || msg.includes('spam')) {
        botResponse = "AI Email Classification rules sort emails by keywords. Spam and Trash emails are stored for 7 days before soft-purging automatically.";
      }

      setChatMessages(prev => [...prev, {
        sender: 'bot',
        message: botResponse,
        timestamp: new Date().toISOString()
      }]);
      setIsBotTyping(false);

      // Show escalation trigger if they ask more than 1 question
      if (unresolvedCount >= 1 || msg.includes('human') || msg.includes('agent') || msg.includes('ticket') || msg.includes('help')) {
        setShowEscalateButton(true);
      }
    }, 1000);
  };

  // Submit Escalated Support Ticket
  const handleSubmitTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerName || !customerEmail || !issueDescription) return;

    try {
      const ticket = await createTicket({
        customerName,
        customerEmail,
        issueDescription,
        chatbotHistory: chatMessages
      });
      setCreatedTicketId(ticket.id);
      
      // Add a message in the chat
      setChatMessages(prev => [...prev, {
        sender: 'bot',
        message: `I have raised a support ticket for you! Your Ticket ID is ${ticket.id}. You can track its status at the top of this portal.`,
        timestamp: new Date().toISOString()
      }]);

      // Reset forms
      setCustomerName('');
      setCustomerEmail('');
      setIssueDescription('');
    } catch (e) {
      console.error(e);
    }
  };

  const handleCloseSuccessScreen = () => {
    setCreatedTicketId(null);
    setIsTicketModalOpen(false);
    setShowEscalateButton(false);
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      
      {/* Brand Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="h-10 w-10 rounded-xl bg-blue-600 flex items-center justify-center text-white font-bold text-xl shadow-lg">
            Ω
          </div>
          <div>
            <h1 className="font-extrabold text-2xl text-slate-800 dark:text-white leading-tight">Antigravity Customer Portal</h1>
            <p className="text-xs text-slate-400 font-medium">Self-Service Help Center & Real-Time Tracking</p>
          </div>
        </div>

        <div className="flex items-center space-x-1.5 text-xs text-slate-500 font-semibold bg-emerald-50 dark:bg-emerald-950/20 text-emerald-600 dark:text-emerald-400 px-3 py-1.5 rounded-full border border-emerald-100 dark:border-emerald-900/30 self-start md:self-auto">
          <ShieldCheck className="h-4 w-4" />
          <span>Secure Client Access</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* LEFT COLUMN: FAQ & Status Tracker (lg:col-span-5) */}
        <div className="lg:col-span-5 space-y-6">
          
          {/* Ticket Status Tracker */}
          <div className="p-6 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-4">
            <h3 className="font-bold text-slate-800 dark:text-white flex items-center space-x-2">
              <Search className="h-5 w-5 text-blue-500" />
              <span>Track Ticket Status</span>
            </h3>
            
            <p className="text-xs text-slate-400 leading-normal">
              Enter your Ticket ID (e.g., #TCK-1001) to check real-time resolution status and communication logs.
            </p>

            <form onSubmit={handleTrackTicket} className="flex gap-2">
              <input
                type="text"
                required
                value={searchTicketId}
                onChange={(e) => setSearchTicketId(e.target.value)}
                placeholder="e.g. #TCK-1001"
                className="flex-1 px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500 font-semibold"
              />
              <button
                type="submit"
                disabled={isTracking}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold rounded-xl text-xs flex items-center justify-center transition-colors"
              >
                {isTracking ? "Searching..." : "Track"}
              </button>
            </form>

            {/* Tracker Result Display */}
            <AnimatePresence mode="wait">
              {trackedTicket && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30 space-y-3 mt-4"
                >
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-sm text-slate-800 dark:text-white">{trackedTicket.id}</span>
                    
                    {/* Status Badge */}
                    <span className={`px-2 py-0.5 rounded font-bold uppercase text-[9px] ${
                      trackedTicket.status === 'Resolved'
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400'
                        : trackedTicket.status === 'In Progress'
                        ? 'bg-blue-100 text-blue-700 dark:bg-blue-950/20 dark:text-blue-400'
                        : 'bg-amber-100 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400'
                    }`}>
                      {trackedTicket.status}
                    </span>
                  </div>

                  {/* Visual Tracker Bar */}
                  <div className="relative pt-2">
                    <div className="flex mb-2 items-center justify-between text-[10px] text-slate-400">
                      <span>Submitted</span>
                      <span>Working</span>
                      <span>Resolved</span>
                    </div>
                    <div className="overflow-hidden h-1.5 text-xs flex rounded bg-slate-200 dark:bg-slate-800">
                      <div 
                        style={{ width: trackedTicket.status === 'Resolved' ? '100%' : trackedTicket.status === 'In Progress' ? '50%' : '15%' }}
                        className="shadow-none flex flex-col text-center whitespace-nowrap text-white justify-center bg-blue-600 transition-all duration-550" 
                      />
                    </div>
                  </div>

                  <div className="text-xs space-y-1.5 pt-2 text-slate-600 dark:text-slate-350">
                    <p><strong>Customer Name:</strong> {trackedTicket.customerName}</p>
                    <p><strong>Issue:</strong> {trackedTicket.issueDescription}</p>
                    {trackedTicket.agentNotes && (
                      <div className="p-3 bg-blue-500/5 rounded-lg border border-blue-500/10 mt-2 text-[11px] text-blue-600 dark:text-blue-450 italic">
                        <strong>Agent Update:</strong> "{trackedTicket.agentNotes}"
                      </div>
                    )}
                  </div>
                </motion.div>
              )}

              {trackError && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="p-3 bg-rose-50 border border-rose-250 text-rose-600 rounded-xl text-xs flex items-center space-x-1.5"
                >
                  <AlertCircle className="h-4 w-4" />
                  <span>{trackError}</span>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* FAQ Accordion */}
          <div className="p-6 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-4">
            <h3 className="font-bold text-slate-850 dark:text-white flex items-center space-x-2">
              <HelpCircle className="h-5 w-5 text-indigo-500" />
              <span>Frequently Asked Questions</span>
            </h3>

            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {FAQ_ITEMS.map((faq, idx) => {
                const isOpen = openFaqIdx === idx;
                return (
                  <div key={idx} className="py-3">
                    <button
                      onClick={() => toggleFaq(idx)}
                      className="w-full flex justify-between items-center text-left text-xs font-bold text-slate-700 dark:text-slate-300 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                    >
                      <span>{faq.q}</span>
                      {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </button>
                    
                    <AnimatePresence>
                      {isOpen && (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          className="text-xs text-slate-400 leading-relaxed mt-2"
                        >
                          {faq.a}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                );
              })}
            </div>
          </div>

        </div>

        {/* RIGHT COLUMN: Chatbot & Escalation (lg:col-span-7) */}
        <div className="lg:col-span-7 p-6 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm flex flex-col h-[580px]">
          
          <div className="flex items-center justify-between pb-4 border-b border-slate-150 dark:border-slate-800">
            <div className="flex items-center space-x-2">
              <MessageSquare className="h-5 w-5 text-blue-500" />
              <div>
                <h3 className="font-bold text-sm text-slate-800 dark:text-white">Self-Service AI Chatbot</h3>
                <span className="text-[10px] text-slate-400 font-semibold flex items-center">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 mr-1 animate-ping" />
                  Bot Online
                </span>
              </div>
            </div>

            {showEscalateButton && (
              <button
                onClick={() => setIsTicketModalOpen(true)}
                className="px-3.5 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-semibold shadow-md shadow-rose-500/10 transition-transform hover:scale-102 flex items-center space-x-1"
              >
                <span>Raise Ticket</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 my-4 bg-slate-50 dark:bg-slate-900/50 rounded-2xl border border-slate-100 dark:border-slate-800/80">
            {chatMessages.map((msg, idx) => {
              const isBot = msg.sender === 'bot';
              return (
                <div key={idx} className={`flex ${isBot ? 'justify-start' : 'justify-end'}`}>
                  <div className={`max-w-[75%] p-3.5 rounded-2xl text-xs leading-relaxed ${
                    isBot
                      ? 'bg-white dark:bg-dark-card border border-slate-150 dark:border-slate-850 text-slate-700 dark:text-slate-350 shadow-xs'
                      : 'bg-blue-600 text-white font-medium shadow-sm'
                  }`}>
                    <span className="block text-[8px] font-bold uppercase tracking-wider mb-1 text-slate-400 dark:text-slate-500">
                      {isBot ? 'Support Bot' : 'You'}
                    </span>
                    <p>{msg.message}</p>
                  </div>
                </div>
              );
            })}

            {isBotTyping && (
              <div className="flex justify-start">
                <div className="p-3 bg-white dark:bg-dark-card border border-slate-100 dark:border-slate-800 rounded-2xl flex items-center space-x-1">
                  <div className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            )}
          </div>

          {/* Chat Form Input */}
          <form onSubmit={handleSendMessage} className="flex gap-2">
            <input
              type="text"
              required
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              placeholder="Type your query here (e.g. 'how to reset password' or 'talk to agent')..."
              className="flex-1 px-4 py-2.5 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-xs outline-none focus:border-blue-500"
            />
            <button
              type="submit"
              className="p-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl flex items-center justify-center shadow-md shadow-blue-500/20"
            >
              <Send className="h-4.5 w-4.5" />
            </button>
          </form>

        </div>

      </div>

      {/* Escalation 'Raise Ticket' Modal */}
      <AnimatePresence>
        {isTicketModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
            <motion.div 
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl"
            >
              {createdTicketId ? (
                // Success screen
                <div className="p-8 text-center space-y-4">
                  <div className="h-12 w-12 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mx-auto">
                    <CheckCircle2 className="h-8 w-8" />
                  </div>
                  <div>
                    <h3 className="font-extrabold text-lg text-slate-850 dark:text-white">Support Ticket Created Successfully!</h3>
                    <p className="text-xs text-slate-400 mt-1">Your ticket has been sent to our human technical queue.</p>
                  </div>
                  
                  <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-900/80 border border-slate-100 dark:border-slate-800 w-full max-w-xs mx-auto">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">Your Ticket ID</span>
                    <strong className="text-2xl font-black text-blue-600 tracking-wider block mt-1">{createdTicketId}</strong>
                  </div>

                  <p className="text-[11px] text-slate-450 leading-relaxed max-w-sm mx-auto">
                    Please copy and save this ID. You can enter it in the "Track Ticket Status" field at the top of the portal anytime to view agent updates.
                  </p>

                  <button
                    onClick={handleCloseSuccessScreen}
                    className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold shadow-md text-sm mt-4"
                  >
                    Got It, Thank You
                  </button>
                </div>
              ) : (
                // Input form screen
                <>
                  <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center bg-slate-50/50 dark:bg-slate-900/20">
                    <div className="flex items-center space-x-2">
                      <Sparkles className="h-5 w-5 text-rose-500" />
                      <h3 className="font-bold text-lg text-slate-800 dark:text-white">Escalate to Tech Support</h3>
                    </div>
                    <button onClick={() => setIsTicketModalOpen(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-white">
                      <X className="h-5 w-5" />
                    </button>
                  </div>
                  <form onSubmit={handleSubmitTicket} className="p-6 space-y-4">
                    <div>
                      <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Your Name *</label>
                      <input
                        type="text"
                        required
                        value={customerName}
                        onChange={(e) => setCustomerName(e.target.value)}
                        placeholder="Bruce Wayne"
                        className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Your Email *</label>
                      <input
                        type="email"
                        required
                        value={customerEmail}
                        onChange={(e) => setCustomerEmail(e.target.value)}
                        placeholder="bruce@waynecorp.com"
                        className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Describe your Technical Issue *</label>
                      <textarea
                        required
                        value={issueDescription}
                        onChange={(e) => setIssueDescription(e.target.value)}
                        rows={3}
                        placeholder="Please details exactly what went wrong. Include error codes if any."
                        className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500 resize-none"
                      />
                    </div>

                    <div className="flex justify-end space-x-3 pt-4 border-t border-slate-200 dark:border-slate-800">
                      <button
                        type="button"
                        onClick={() => setIsTicketModalOpen(false)}
                        className="px-4 py-2 rounded-xl text-sm font-semibold border border-slate-200 dark:border-slate-700 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold shadow-md shadow-blue-500/20"
                      >
                        Submit Support Ticket
                      </button>
                    </div>
                  </form>
                </>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
