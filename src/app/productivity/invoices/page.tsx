'use client';

import { useState, useEffect } from 'react';
import { getInvoices, saveInvoice } from '@/app/actions';
import { Invoice, InvoiceItem } from '@/lib/types';
import { 
  FileText, 
  Plus, 
  Trash2, 
  Download, 
  Mail, 
  Check, 
  Calculator,
  User,
  PlusCircle,
  Eye,
  AlertCircle
} from 'lucide-react';
import { motion } from 'framer-motion';

export default function InvoiceGeneratorPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);

  // Form states
  const [clientName, setClientName] = useState('Wayne Enterprises');
  const [clientEmail, setClientEmail] = useState('billing@waynecorp.com');
  const [invoiceNumber, setInvoiceNumber] = useState('INV-2026-003');
  const [taxRate, setTaxRate] = useState(8);
  const [items, setItems] = useState<InvoiceItem[]>([
    { id: '1', description: 'Enterprise AI Suite Integration', qty: 1, unitPrice: 7500 },
    { id: '2', description: 'Priority Support & Consulting (Hours)', qty: 15, unitPrice: 150 }
  ]);

  const [simulatingEmail, setSimulatingEmail] = useState(false);
  const [emailStatus, setEmailStatus] = useState<string | null>(null);

  // Fetch past invoices
  useEffect(() => {
    const fetchInvoices = async () => {
      setLoading(true);
      try {
        const list = await getInvoices();
        setInvoices(list);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchInvoices();
  }, []);

  // Recalculate totals
  const subtotal = items.reduce((sum, item) => sum + (item.qty * item.unitPrice), 0);
  const taxAmount = (subtotal * taxRate) / 100;
  const total = subtotal + taxAmount;

  // Add Item Row
  const handleAddItem = () => {
    const newItem: InvoiceItem = {
      id: Math.random().toString(36).substr(2, 9),
      description: 'New service line item',
      qty: 1,
      unitPrice: 100
    };
    setItems([...items, newItem]);
  };

  // Update Item Row
  const handleUpdateItem = (id: string, field: keyof InvoiceItem, value: any) => {
    setItems(items.map(item => {
      if (item.id === id) {
        if (field === 'qty') return { ...item, qty: Math.max(1, parseInt(value) || 0) };
        if (field === 'unitPrice') return { ...item, unitPrice: Math.max(0, parseFloat(value) || 0) };
        return { ...item, [field]: value };
      }
      return item;
    }));
  };

  // Remove Item Row
  const handleRemoveItem = (id: string) => {
    if (items.length <= 1) return; // Keep at least one item
    setItems(items.filter(item => item.id !== id));
  };

  // PDF Generation Trigger
  const handleExportPDF = async () => {
    try {
      // Import jspdf dynamically to avoid SSR errors
      const { jsPDF } = await import('jspdf');
      const autoTable = (await import('jspdf-autotable')).default;

      const doc = new jsPDF();

      // Premium styling colors
      const blue: [number, number, number] = [2, 132, 199];
      const darkSlate: [number, number, number] = [15, 23, 42];

      // Document Header
      doc.setFillColor(blue[0], blue[1], blue[2]);
      doc.rect(0, 0, 210, 35, 'F');

      doc.setTextColor(255, 255, 255);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(22);
      doc.text("ANTIGRAVITY SUITE", 15, 22);

      doc.setFontSize(10);
      doc.setFont("helvetica", "normal");
      doc.text("INVOICE STATEMENT", 15, 28);

      // Invoice info block (Top-right)
      doc.setTextColor(255, 255, 255);
      doc.setFont("helvetica", "bold");
      doc.text(`Invoice #: ${invoiceNumber}`, 150, 18);
      doc.setFont("helvetica", "normal");
      doc.text(`Date: ${new Date().toLocaleDateString()}`, 150, 24);
      doc.text("Status: UNPAID", 150, 30);

      // Billing details
      doc.setTextColor(darkSlate[0], darkSlate[1], darkSlate[2]);
      doc.setFontSize(10);
      doc.setFont("helvetica", "bold");
      doc.text("FROM:", 15, 50);
      doc.setFont("helvetica", "normal");
      doc.text("Antigravity Inc.", 15, 56);
      doc.text("100 Innovation Way", 15, 62);
      doc.text("founder@antigravity.io", 15, 68);

      doc.setFont("helvetica", "bold");
      doc.text("BILL TO:", 110, 50);
      doc.setFont("helvetica", "normal");
      doc.text(clientName, 110, 56);
      doc.text(clientEmail || "billing@client.com", 110, 62);

      // Item table headers
      const tableHeaders = [["Description", "Qty", "Unit Price", "Total"]];
      const tableRows = items.map(item => [
        item.description,
        item.qty.toString(),
        `$${item.unitPrice.toLocaleString()}`,
        `$${(item.qty * item.unitPrice).toLocaleString()}`
      ]);

      // Draw table
      autoTable(doc, {
        head: tableHeaders,
        body: tableRows,
        startY: 80,
        theme: 'grid',
        headStyles: {
          fillColor: blue,
          textColor: [255, 255, 255],
          fontStyle: 'bold'
        },
        alternateRowStyles: {
          fillColor: [248, 250, 252]
        },
        columnStyles: {
          0: { cellWidth: 100 },
          1: { cellWidth: 20, halign: 'center' },
          2: { cellWidth: 35, halign: 'right' },
          3: { cellWidth: 35, halign: 'right' }
        }
      });

      // Totals box
      const finalY = (doc as any).lastAutoTable.finalY + 10;
      doc.setFont("helvetica", "bold");
      doc.text("Payment Terms: Net 30", 15, finalY + 10);
      doc.setFont("helvetica", "normal");
      doc.text("Please wire funds to Bank of Silicon Valley", 15, finalY + 16);

      doc.setFont("helvetica", "normal");
      doc.text("Subtotal:", 130, finalY + 10);
      doc.text(`$${subtotal.toLocaleString()}`, 175, finalY + 10, { align: 'right' });
      
      doc.text(`Tax (${taxRate}%):`, 130, finalY + 16);
      doc.text(`$${taxAmount.toLocaleString()}`, 175, finalY + 16, { align: 'right' });

      doc.setFont("helvetica", "bold");
      doc.text("Total Due:", 130, finalY + 24);
      doc.text(`$${total.toLocaleString()}`, 175, finalY + 24, { align: 'right' });

      // Save PDF
      doc.save(`invoice_${invoiceNumber}.pdf`);

      // Add to database logs
      const newInvoice: Invoice = {
        id: `inv-${Math.random().toString(36).substr(2, 9)}`,
        invoiceNumber,
        clientName,
        clientEmail,
        items,
        taxRate,
        total,
        status: 'Unpaid',
        createdAt: new Date().toISOString()
      };
      
      await saveInvoice(newInvoice);
      setInvoices([newInvoice, ...invoices]);
    } catch (e) {
      console.error("PDF generation error", e);
    }
  };

  // Simulating Client Delivery
  const handleSendEmail = () => {
    setSimulatingEmail(true);
    setEmailStatus("Generating PDF attachment...");
    setTimeout(() => {
      setEmailStatus("Sending wire instructions...");
      setTimeout(() => {
        setEmailStatus(null);
        setSimulatingEmail(false);
        alert(`Invoice successfully emailed to ${clientEmail}!`);
      }, 1500);
    }, 1500);
  };

  return (
    <div className="space-y-6">
      
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* LEFT COLUMN: Input Form (lg:col-span-7) */}
        <div className="lg:col-span-7 p-6 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-6">
          <div className="flex items-center space-x-2 pb-4 border-b border-slate-200 dark:border-slate-800">
            <Calculator className="h-5 w-5 text-blue-500" />
            <h3 className="font-bold text-slate-800 dark:text-white font-lg">Billing Form</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Invoice #</label>
              <input
                type="text"
                value={invoiceNumber}
                onChange={(e) => setInvoiceNumber(e.target.value)}
                className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500 font-semibold"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Client Name</label>
              <input
                type="text"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500 font-medium"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase mb-1.5">Client Email</label>
              <input
                type="email"
                value={clientEmail}
                onChange={(e) => setClientEmail(e.target.value)}
                className="w-full px-4 py-2 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-xl text-sm outline-none focus:border-blue-500"
              />
            </div>
          </div>

          {/* Item Lines */}
          <div className="space-y-3">
            <div className="flex justify-between items-center pb-2">
              <label className="block text-xs font-bold text-slate-400 uppercase">Itemized Line Services</label>
              <button
                onClick={handleAddItem}
                className="flex items-center space-x-1.5 text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 font-semibold"
              >
                <PlusCircle className="h-4 w-4" />
                <span>Add Item</span>
              </button>
            </div>

            <div className="space-y-3 max-h-60 overflow-y-auto pr-1">
              {items.map((item, idx) => (
                <div key={item.id} className="flex flex-col sm:flex-row gap-3 p-3 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-xl items-stretch sm:items-center">
                  <span className="text-xs text-slate-400 font-bold self-center sm:self-auto min-w-[20px]">#{idx + 1}</span>
                  
                  <div className="flex-1">
                    <input
                      type="text"
                      placeholder="Service description"
                      value={item.description}
                      onChange={(e) => handleUpdateItem(item.id, 'description', e.target.value)}
                      className="w-full px-3 py-1.5 border border-slate-250 dark:border-slate-700 bg-white dark:bg-slate-950 rounded-lg text-xs outline-none focus:border-blue-500"
                    />
                  </div>
                  
                  <div className="w-20">
                    <input
                      type="number"
                      min={1}
                      placeholder="Qty"
                      value={item.qty}
                      onChange={(e) => handleUpdateItem(item.id, 'qty', e.target.value)}
                      className="w-full px-3 py-1.5 border border-slate-250 dark:border-slate-700 bg-white dark:bg-slate-950 rounded-lg text-xs outline-none text-center focus:border-blue-500"
                    />
                  </div>

                  <div className="w-32">
                    <input
                      type="number"
                      min={0}
                      placeholder="Unit Price ($)"
                      value={item.unitPrice}
                      onChange={(e) => handleUpdateItem(item.id, 'unitPrice', e.target.value)}
                      className="w-full px-3 py-1.5 border border-slate-250 dark:border-slate-700 bg-white dark:bg-slate-950 rounded-lg text-xs outline-none text-right focus:border-blue-500"
                    />
                  </div>

                  <button
                    onClick={() => handleRemoveItem(item.id)}
                    disabled={items.length <= 1}
                    className="p-1.5 text-slate-400 hover:text-rose-500 dark:hover:text-rose-450 hover:bg-slate-200 dark:hover:bg-slate-800 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition-colors self-end sm:self-auto"
                  >
                    <Trash2 className="h-4.5 w-4.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Tax Setting */}
          <div className="pt-4 border-t border-slate-100 dark:border-slate-850 flex justify-between items-center">
            <div className="flex items-center space-x-2">
              <label className="text-xs font-bold text-slate-400 uppercase">Tax Rate (%)</label>
              <input
                type="number"
                min={0}
                max={100}
                value={taxRate}
                onChange={(e) => setTaxRate(Math.max(0, parseFloat(e.target.value) || 0))}
                className="w-16 px-2 py-1 border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 rounded-lg text-xs outline-none focus:border-blue-500 text-center font-bold"
              />
            </div>

            <div className="text-right space-y-1">
              <p className="text-xs text-slate-400">Subtotal: <strong className="text-slate-600 dark:text-slate-200">${subtotal.toLocaleString()}</strong></p>
              <p className="text-xs text-slate-400">Tax ({taxRate}%): <strong className="text-slate-600 dark:text-slate-200">${taxAmount.toLocaleString()}</strong></p>
              <h4 className="font-bold text-lg text-blue-600 dark:text-blue-400">Total: ${total.toLocaleString()}</h4>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex flex-col sm:flex-row gap-3 pt-4 border-t border-slate-200 dark:border-slate-800">
            <button
              onClick={handleExportPDF}
              className="flex-1 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold shadow-md shadow-blue-500/20 hover:-translate-y-0.5 transition-all duration-200 flex items-center justify-center space-x-2"
            >
              <Download className="h-5 w-5" />
              <span>Export & Save PDF</span>
            </button>

            <button
              onClick={handleSendEmail}
              disabled={simulatingEmail}
              className="py-3 px-6 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 rounded-xl font-semibold hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors disabled:opacity-50 flex items-center justify-center space-x-2"
            >
              {simulatingEmail ? (
                <>
                  <div className="h-4.5 w-4.5 rounded-full border-2 border-slate-400 border-t-transparent animate-spin" />
                  <span className="text-xs">{emailStatus}</span>
                </>
              ) : (
                <>
                  <Mail className="h-5 w-5" />
                  <span>Send to Client</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* RIGHT COLUMN: Real-Time Preview Panel (lg:col-span-5) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="p-4 bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl flex items-center space-x-2">
            <Eye className="h-5 w-5 text-indigo-500" />
            <h4 className="font-bold text-slate-700 dark:text-slate-300 text-sm">Real-Time Invoice Preview</h4>
          </div>

          {/* Paper Mockup Card */}
          <div className="bg-white text-slate-800 border border-slate-300 rounded-2xl shadow-xl overflow-hidden min-h-[500px] flex flex-col justify-between font-sans relative">
            {/* Header band */}
            <div className="bg-slate-900 text-white p-6 flex justify-between items-start">
              <div>
                <h3 className="font-bold text-sm tracking-widest text-blue-400">ANTIGRAVITY</h3>
                <p className="text-[10px] text-slate-400 font-medium">Business Operations Platform</p>
              </div>
              <div className="text-right">
                <h4 className="font-bold text-xs uppercase text-slate-300">INVOICE</h4>
                <p className="text-[10px] text-slate-400">{invoiceNumber}</p>
                <p className="text-[8px] text-slate-500">{new Date().toLocaleDateString()}</p>
              </div>
            </div>

            {/* Bill Info */}
            <div className="p-6 grid grid-cols-2 gap-4 border-b border-slate-100 text-xs">
              <div>
                <span className="font-bold text-[9px] uppercase tracking-wider text-slate-400">FROM</span>
                <p className="font-bold text-slate-700 mt-1">Antigravity Inc.</p>
                <p className="text-slate-500 text-[10px]">100 Innovation Way</p>
                <p className="text-slate-500 text-[10px]">founder@antigravity.io</p>
              </div>

              <div>
                <span className="font-bold text-[9px] uppercase tracking-wider text-slate-400">BILL TO</span>
                <p className="font-bold text-slate-700 mt-1">{clientName}</p>
                <p className="text-slate-500 text-[10px] truncate">{clientEmail}</p>
              </div>
            </div>

            {/* Line items table */}
            <div className="p-6 flex-1 text-xs">
              <div className="grid grid-cols-12 font-bold text-[9px] uppercase text-slate-400 tracking-wider pb-2 border-b border-slate-150">
                <div className="col-span-6">Description</div>
                <div className="col-span-2 text-center">Qty</div>
                <div className="col-span-2 text-right">Unit</div>
                <div className="col-span-2 text-right">Total</div>
              </div>

              <div className="divide-y divide-slate-100 mt-2 max-h-52 overflow-y-auto">
                {items.map((item) => (
                  <div key={item.id} className="grid grid-cols-12 py-2 text-[11px] text-slate-600 font-medium">
                    <div className="col-span-6 truncate" title={item.description}>{item.description}</div>
                    <div className="col-span-2 text-center">{item.qty}</div>
                    <div className="col-span-2 text-right">${item.unitPrice.toLocaleString()}</div>
                    <div className="col-span-2 text-right">${(item.qty * item.unitPrice).toLocaleString()}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Total summary */}
            <div className="p-6 bg-slate-50 border-t border-slate-100 text-xs flex justify-between items-end">
              <div className="space-y-1 text-slate-450 text-[10px]">
                <p>Terms: Net 30 days payment receipt</p>
                <p>Thank you for your business!</p>
              </div>
              <div className="w-48 text-right space-y-1.5">
                <div className="flex justify-between text-slate-500 text-[11px]">
                  <span>Subtotal:</span>
                  <span>${subtotal.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-slate-500 text-[11px]">
                  <span>Tax ({taxRate}%):</span>
                  <span>${taxAmount.toLocaleString()}</span>
                </div>
                <div className="flex justify-between font-bold text-slate-800 text-[13px] pt-1.5 border-t border-slate-200">
                  <span>Total Due:</span>
                  <span className="text-blue-600">${total.toLocaleString()}</span>
                </div>
              </div>
            </div>

          </div>
        </div>

      </div>

      {/* Invoice History / Database log list */}
      <div className="p-6 bg-white dark:bg-dark-card border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm">
        <h3 className="font-bold text-slate-850 dark:text-white mb-4">Invoice Ledger History</h3>
        
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 text-xs font-semibold text-slate-400 uppercase">
                <th className="py-3 px-4">Invoice Number</th>
                <th className="py-3 px-4">Client</th>
                <th className="py-3 px-4">Created Date</th>
                <th className="py-3 px-4 text-right">Grand Total</th>
                <th className="py-3 px-4 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-xs text-slate-600 dark:text-slate-400">
              {loading ? (
                <tr>
                  <td colSpan={5} className="py-6 text-center">Loading ledger history...</td>
                </tr>
              ) : invoices.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-6 text-center">No invoices logged. Generate one above!</td>
                </tr>
              ) : (
                invoices.map((inv) => (
                  <tr key={inv.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-900/10">
                    <td className="py-3 px-4 font-bold text-slate-800 dark:text-white">{inv.invoiceNumber}</td>
                    <td className="py-3 px-4">{inv.clientName}</td>
                    <td className="py-3 px-4">{new Date(inv.createdAt).toLocaleDateString()}</td>
                    <td className="py-3 px-4 text-right font-semibold">${inv.total.toLocaleString()}</td>
                    <td className="py-3 px-4 text-center">
                      <span className={`px-2 py-0.5 rounded font-bold uppercase text-[9px] ${
                        inv.status === 'Paid'
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400'
                          : 'bg-amber-100 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400'
                      }`}>
                        {inv.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}
