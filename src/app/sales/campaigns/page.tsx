'use client';

import { useState, useEffect } from 'react';
import { getCampaigns, saveCampaign } from '@/app/actions';
import { Campaign } from '@/lib/types';
import { 
  Send, 
  Plus, 
  Play, 
  Pause, 
  MessageSquare, 
  Percent, 
  Zap, 
  ListOrdered, 
  Edit3, 
  Save, 
  HelpCircle,
  Sparkles,
  ArrowRight,
  UserCheck
} from 'lucide-react';
import { motion } from 'framer-motion';

// Mock Objection Rules for the simulator
const INITIAL_OBJECTION_RULES = [
  {
    id: 'obj-1',
    name: 'Price / Budget Objection',
    keywords: ['expensive', 'budget', 'price', 'cost', 'money', 'afford'],
    reply: "I completely understand that budget is top of mind right now. To help, we can structure this into a flexible monthly tier or offer a 14-day trial so you can measure the ROI first. Would that help make this viable?"
  },
  {
    id: 'obj-2',
    name: 'Competitor / Already Using Tool',
    keywords: ['competitor', 'already use', 'salesforce', 'hubspot', 'another tool', 'happy with'],
    reply: "Hubspot/Salesforce are great tools! Antigravity actually sits right alongside them to automate actions they don't cover natively—specifically our custom AI email filter and direct cold call logger. Let me show you how we integrate to save 10 hours a week."
  },
  {
    id: 'obj-3',
    name: 'Timing / Too Busy',
    keywords: ['busy', 'no time', 'later', 'next quarter', 'next year', 'currently scaling'],
    reply: "I get it, you are flat out! No pressure at all. I can drop you a quick 2-minute video overview so you can watch it at your convenience, and we can check back in next month. Does that sound fair?"
  },
  {
    id: 'obj-4',
    name: 'Generic Dismissal / Email request',
    keywords: ['send email', 'send info', 'not interested', 'unsubscribe'],
    reply: "No worries! I will send over our 1-page case study to this address. If it sparks any interest in the future, you know where to find us. Have a productive week!"
  }
];

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null);
  
  // Create / Edit Campaign state
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState('');
  const [template, setTemplate] = useState('');
  const [delayDays, setDelayDays] = useState(2);
  const [maxFollowUps, setMaxFollowUps] = useState(3);

  // Simulator state
  const [objectionRules, setObjectionRules] = useState(INITIAL_OBJECTION_RULES);
  const [simulatedName, setSimulatedName] = useState('Bruce Wayne');
  const [simulatedObjection, setSimulatedObjection] = useState('Your service is way too expensive for our current stage.');
  const [detectedRule, setDetectedRule] = useState<string | null>(null);
  const [generatedReply, setGeneratedReply] = useState<string | null>(null);
  
  // Custom objection rule add
  const [newRuleName, setNewRuleName] = useState('');
  const [newRuleKeywords, setNewRuleKeywords] = useState('');
  const [newRuleReply, setNewRuleReply] = useState('');
  const [showAddRuleForm, setShowAddRuleForm] = useState(false);

  // Fetch campaigns
  const fetchCampaigns = async () => {
    try {
      const data = await getCampaigns();
      setCampaigns(data);
      if (data.length > 0) {
        setSelectedCampaign(data[0]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchCampaigns();
  }, []);

  const handleSelectCampaign = (campaign: Campaign) => {
    setSelectedCampaign(campaign);
    setIsEditing(false);
  };

  const handleStartCreate = () => {
    setSelectedCampaign(null);
    setIsEditing(true);
    setName('');
    setTemplate('Hi {{name}},\n\nI noticed you are building... [Write Template]');
    setDelayDays(2);
    setMaxFollowUps(3);
  };

  const handleStartEdit = () => {
    if (!selectedCampaign) return;
    setIsEditing(true);
    setName(selectedCampaign.name);
    setTemplate(selectedCampaign.template);
    setDelayDays(selectedCampaign.sequenceRules.delayDays);
    setMaxFollowUps(selectedCampaign.sequenceRules.maxFollowUps);
  };

  const handleSaveCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !template) return;

    const newCampaign: Campaign = {
      id: selectedCampaign ? selectedCampaign.id : `camp-${Math.random().toString(36).substr(2, 9)}`,
      name,
      template,
      sequenceRules: {
        delayDays,
        maxFollowUps
      },
      status: selectedCampaign ? selectedCampaign.status : 'active',
      createdAt: selectedCampaign ? selectedCampaign.createdAt : new Date().toISOString(),
      repliesCount: selectedCampaign ? selectedCampaign.repliesCount : 0,
      objectionsCount: selectedCampaign ? selectedCampaign.objectionsCount : 0
    };

    const saved = await saveCampaign(newCampaign);
    
    // Update local state
    if (selectedCampaign) {
      setCampaigns(campaigns.map(c => c.id === saved.id ? saved : c));
    } else {
      setCampaigns([...campaigns, saved]);
    }
    
    setSelectedCampaign(saved);
    setIsEditing(false);
  };

  const handleToggleStatus = async (campaign: Campaign) => {
    const updated: Campaign = {
      ...campaign,
      status: campaign.status === 'active' ? 'paused' : 'active'
    };
    const saved = await saveCampaign(updated);
    setCampaigns(campaigns.map(c => c.id === saved.id ? saved : c));
    if (selectedCampaign?.id === saved.id) {
      setSelectedCampaign(saved);
    }
  };

  // Run Objection simulation
  const handleSimulateReply = () => {
    const text = simulatedObjection.toLowerCase();
    let matchedRule = null;

    for (const rule of objectionRules) {
      const isMatch = rule.keywords.some(kw => text.includes(kw.toLowerCase()));
      if (isMatch) {
        matchedRule = rule;
        break;
      }
    }

    if (matchedRule) {
      setDetectedRule(matchedRule.name);
      
      // Personalize reply
      let replyText = matchedRule.reply;
      if (selectedCampaign) {
        replyText = replyText.replace('Antigravity', selectedCampaign.name);
      }
      setGeneratedReply(replyText);
    } else {
      setDetectedRule("Unknown/Custom Objection");
      setGeneratedReply("Thanks for sharing that. I want to make sure I answer you correctly—could you clarify what specifically stands in the way of us moving forward?");
    }
  };

  const handleAddCustomRule = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRuleName || !newRuleKeywords || !newRuleReply) return;

    const newRule = {
      id: `rule-${Math.random().toString(36).substr(2, 9)}`,
      name: newRuleName,
      keywords: newRuleKeywords.split(',').map(kw => kw.trim()),
      reply: newRuleReply
    };

    setObjectionRules([...objectionRules, newRule]);
    setShowAddRuleForm(false);
    setNewRuleName('');
    setNewRuleKeywords('');
    setNewRuleReply('');
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      {/* LEFT PANEL: Campaigns List */}
      <div className="space-y-6 lg:col-span-1">
        <div className="p-5 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="font-bold text-slate-800 dark:text-white">Active Campaigns</h3>
            <button
              onClick={handleStartCreate}
              className="p-1.5 bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 rounded-lg transition-colors"
              title="Create New Campaign"
            >
              <Plus className="h-4.5 w-4.5" />
            </button>
          </div>

          <div className="space-y-3">
            {campaigns.map((camp) => {
              const isSelected = selectedCampaign?.id === camp.id;
              return (
                <div
                  key={camp.id}
                  onClick={() => handleSelectCampaign(camp)}
                  className={`p-4 rounded-xl border cursor-pointer transition-all duration-200 ${
                    isSelected 
                      ? 'border-blue-500 bg-blue-50/10 dark:bg-blue-950/10' 
                      : 'border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-900/30'
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <h4 className="font-bold text-sm text-slate-800 dark:text-white truncate max-w-[140px]" title={camp.name}>
                      {camp.name}
                    </h4>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleToggleStatus(camp);
                      }}
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                        camp.status === 'active'
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400'
                          : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                      }`}
                    >
                      {camp.status}
                    </button>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-2 mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-400">
                    <div>
                      <span className="font-medium text-slate-600 dark:text-slate-300">{camp.repliesCount}</span> Replies
                    </div>
                    <div>
                      <span className="font-medium text-slate-600 dark:text-slate-300">{camp.objectionsCount}</span> Objections
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Objection Keyword Settings */}
        <div className="p-5 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm">
          <div className="flex justify-between items-center mb-3">
            <h4 className="font-bold text-sm text-slate-800 dark:text-white">Objection Handling Rules</h4>
            <button
              onClick={() => setShowAddRuleForm(!showAddRuleForm)}
              className="text-xs text-blue-600 dark:text-blue-400 font-semibold hover:underline"
            >
              {showAddRuleForm ? 'Cancel' : '+ Add Rule'}
            </button>
          </div>

          {showAddRuleForm ? (
            <form onSubmit={handleAddCustomRule} className="space-y-3 pt-2">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Rule Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Security Concerns"
                  value={newRuleName}
                  onChange={(e) => setNewRuleName(e.target.value)}
                  className="w-full px-3 py-1.5 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Keywords (comma-separated)</label>
                <input
                  type="text"
                  required
                  placeholder="gdpr, security, safety, firewall"
                  value={newRuleKeywords}
                  onChange={(e) => setNewRuleKeywords(e.target.value)}
                  className="w-full px-3 py-1.5 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Automatic Objection Response</label>
                <textarea
                  required
                  rows={2}
                  placeholder="We take safety seriously. We are GDPR compliant..."
                  value={newRuleReply}
                  onChange={(e) => setNewRuleReply(e.target.value)}
                  className="w-full px-3 py-1.5 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs outline-none focus:border-blue-500 resize-none"
                />
              </div>
              <button
                type="submit"
                className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold"
              >
                Save Rule
              </button>
            </form>
          ) : (
            <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
              {objectionRules.map((rule) => (
                <div key={rule.id} className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800/80 text-xs">
                  <p className="font-bold text-slate-700 dark:text-slate-300">{rule.name}</p>
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {rule.keywords.map(kw => (
                      <span key={kw} className="px-1.5 py-0.5 rounded bg-slate-200/60 dark:bg-slate-800 text-[10px] text-slate-500 font-medium">
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* RIGHT PANEL: Edit & Simulators */}
      <div className="lg:col-span-2 space-y-6">
        
        {/* Campaign Template Form / Viewer */}
        <div className="p-6 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm">
          {isEditing ? (
            <form onSubmit={handleSaveCampaign} className="space-y-4">
              <div className="flex justify-between items-center pb-4 border-b border-slate-200 dark:border-slate-800">
                <h3 className="font-bold text-slate-800 dark:text-white">
                  {selectedCampaign ? 'Edit Campaign Details' : 'Create Outreach Campaign'}
                </h3>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Campaign Name</label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Post-Seed Series A Outreach"
                    className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500"
                  />
                </div>
                
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Delay (Days)</label>
                    <input
                      type="number"
                      required
                      min={1}
                      value={delayDays}
                      onChange={(e) => setDelayDays(Number(e.target.value))}
                      className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Max Followups</label>
                    <input
                      type="number"
                      required
                      min={1}
                      value={maxFollowUps}
                      onChange={(e) => setMaxFollowUps(Number(e.target.value))}
                      className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500"
                    />
                  </div>
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <label className="block text-xs font-bold text-slate-400 uppercase">Sequence Message Template</label>
                  <span className="text-[10px] text-slate-400">Use <code>{"{{name}}"}</code> to insert lead name.</span>
                </div>
                <textarea
                  required
                  rows={6}
                  value={template}
                  onChange={(e) => setTemplate(e.target.value)}
                  className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500 font-mono"
                />
              </div>

              <div className="flex justify-end space-x-3 pt-4 border-t border-slate-200 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsEditing(false)}
                  className="px-4 py-2 rounded-xl text-sm font-semibold border border-slate-200 dark:border-slate-700 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex items-center space-x-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold shadow-md"
                >
                  <Save className="h-4 w-4" />
                  <span>Save Campaign</span>
                </button>
              </div>
            </form>
          ) : selectedCampaign ? (
            <div className="space-y-4">
              <div className="flex justify-between items-center pb-4 border-b border-slate-200 dark:border-slate-800">
                <div>
                  <h3 className="font-bold text-lg text-slate-800 dark:text-white">{selectedCampaign.name}</h3>
                  <p className="text-xs text-slate-400 mt-1">Created on {new Date(selectedCampaign.createdAt).toLocaleDateString()}</p>
                </div>
                <div className="flex space-x-2">
                  <button
                    onClick={() => handleToggleStatus(selectedCampaign)}
                    className={`p-2 border rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors ${
                      selectedCampaign.status === 'active' ? 'text-amber-500 border-amber-200' : 'text-emerald-500 border-emerald-200'
                    }`}
                    title={selectedCampaign.status === 'active' ? 'Pause Campaign' : 'Resume Campaign'}
                  >
                    {selectedCampaign.status === 'active' ? <Pause className="h-4.5 w-4.5" /> : <Play className="h-4.5 w-4.5" />}
                  </button>
                  <button
                    onClick={handleStartEdit}
                    className="p-2 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-xl transition-colors text-slate-600 dark:text-slate-300"
                    title="Edit Template"
                  >
                    <Edit3 className="h-4.5 w-4.5" />
                  </button>
                </div>
              </div>

              {/* Template Body Card */}
              <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 font-mono text-sm whitespace-pre-wrap text-slate-700 dark:text-slate-300">
                {selectedCampaign.template}
              </div>

              {/* Rules summary badges */}
              <div className="flex items-center space-x-6 text-xs text-slate-400 bg-slate-50/50 dark:bg-slate-900/30 p-3 rounded-xl">
                <div className="flex items-center space-x-2">
                  <Zap className="h-4 w-4 text-blue-500" />
                  <span>Send delay: <strong>{selectedCampaign.sequenceRules.delayDays} days</strong></span>
                </div>
                <div className="h-4 w-px bg-slate-200 dark:bg-slate-800" />
                <div className="flex items-center space-x-2">
                  <ListOrdered className="h-4 w-4 text-purple-500" />
                  <span>Max sequence follow-ups: <strong>{selectedCampaign.sequenceRules.maxFollowUps} times</strong></span>
                </div>
              </div>
            </div>
          ) : (
            <div className="py-12 text-center text-slate-400">
              <p>No campaign selected. Click + to create your first outreach sequence.</p>
            </div>
          )}
        </div>

        {/* Interactive Objection Reply Simulator */}
        <div className="p-6 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-4">
          <div className="flex items-center space-x-2">
            <Sparkles className="h-5 w-5 text-indigo-500" />
            <h3 className="font-bold text-slate-800 dark:text-white">Objection Reply Simulator</h3>
          </div>
          
          <p className="text-xs text-slate-400 leading-normal">
            Simulate an incoming client objection. The platform scans keywords against your objection rules to suggest the optimal response instantly.
          </p>

          <div className="space-y-3 pt-2">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Simulate Lead Name</label>
                <input
                  type="text"
                  value={simulatedName}
                  onChange={(e) => setSimulatedName(e.target.value)}
                  className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Quick Presets</label>
                <select
                  onChange={(e) => setSimulatedObjection(e.target.value)}
                  className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500 appearance-none cursor-pointer"
                >
                  <option value="Your service is way too expensive for our current stage.">Price Objection ("expensive")</option>
                  <option value="We are already using Salesforce and HubSpot, so we have no need for this.">Competitor Objection ("already use")</option>
                  <option value="I am in the middle of scaling our engineering team, call me back next quarter.">Timing Objection ("busy")</option>
                  <option value="Please just send me an email with the product sheet.">Generic / Unsubscribe ("send email")</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Client Response / Objection</label>
              <textarea
                rows={2}
                value={simulatedObjection}
                onChange={(e) => setSimulatedObjection(e.target.value)}
                className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500 resize-none font-medium"
              />
            </div>

            <button
              onClick={handleSimulateReply}
              className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-semibold shadow-md shadow-indigo-500/20 hover:-translate-y-0.5 transition-all duration-200 flex items-center justify-center space-x-2"
            >
              <span>Run Automated Objection Handler</span>
              <ArrowRight className="h-4.5 w-4.5" />
            </button>

            {/* Generated Reply Card */}
            {generatedReply && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-5 border border-slate-200 dark:border-slate-800 rounded-2xl bg-gradient-to-br from-slate-50 to-blue-50/10 dark:from-slate-900 dark:to-blue-950/5 space-y-3"
              >
                <div className="flex justify-between items-center">
                  <span className="text-[10px] font-bold text-indigo-600 dark:text-indigo-400 uppercase tracking-widest bg-indigo-50 dark:bg-indigo-950/40 px-2 py-0.5 rounded">
                    Detected Objection: {detectedRule}
                  </span>
                  <span className="text-xs text-slate-400 flex items-center">
                    <UserCheck className="h-3.5 w-3.5 mr-1 text-emerald-500" />
                    Objection Solved
                  </span>
                </div>
                
                <p className="text-xs text-slate-400 font-bold uppercase mt-1">Suggested Follow-Up Response:</p>
                <div className="p-3.5 rounded-xl bg-white dark:bg-slate-950 border border-slate-100 dark:border-slate-900 text-sm text-slate-700 dark:text-slate-300 italic whitespace-pre-line leading-relaxed shadow-sm">
                  {`Hi ${simulatedName},\n\n${generatedReply}`}
                </div>

                <div className="flex justify-between items-center text-[10px] text-slate-400 pt-2">
                  <span>Sequence Follow-Up Rule: Active</span>
                  <span>Auto-reschedules call queue in 3 days</span>
                </div>
              </motion.div>
            )}

          </div>
        </div>

      </div>
    </div>
  );
}
