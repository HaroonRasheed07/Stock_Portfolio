"use client";

import { useState } from "react";
import { uploadFileAPI, fetchAPI } from "@/lib/api";
import { Upload, FileText, CheckCircle, AlertCircle, ArrowRight } from "lucide-react";
import { formatCurrency } from "@/lib/utils";

export default function PortfolioPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setPreview(null);
      setError(null);
      setSuccessMsg(null);
    }
  };

  const handleUploadPreview = async () => {
    if (!file) return;
    try {
      setLoading(true);
      setError(null);
      const formData = new FormData();
      formData.append("file", file);

      const res = await uploadFileAPI<any>("/portfolio/import/preview", formData);
      setPreview(res);
    } catch (err: any) {
      setError(err.message || "Failed to parse CSV file.");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmImport = async () => {
    if (!preview) return;
    try {
      setConfirming(true);
      setError(null);
      const res = await fetchAPI<any>("/portfolio/import/confirm", {
        method: "POST",
        body: JSON.stringify(preview),
      });

      setSuccessMsg(`Successfully imported ${res.imported_count} holdings. Total portfolio value: ${formatCurrency(res.total_value)}`);
      setPreview(null);
      setFile(null);
    } catch (err: any) {
      setError(err.message || "Failed to confirm import.");
    } finally {
      setConfirming(false);
    }
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Portfolio Import & Snapshots</h1>
        <p className="text-xs text-slate-400 mt-1">
          Upload your brokerage summary CSV to update portfolio holdings. History snapshots are automatically preserved.
        </p>
      </div>

      {/* Upload Dropzone */}
      <div className="bg-[#121824] border-2 border-dashed border-[#1e293b] hover:border-sky-500/40 rounded-xl p-8 text-center transition-colors">
        <Upload className="w-12 h-12 text-sky-400 mx-auto mb-3" />
        <h3 className="text-sm font-semibold text-slate-200">Select Brokerage Summary CSV</h3>
        <p className="text-xs text-slate-400 mt-1 mb-4">Supports standard brokerage CSV exports (Symbol, Quantity, Cost Basis, Value)</p>
        
        <input
          type="file"
          accept=".csv"
          onChange={handleFileChange}
          className="hidden"
          id="csv-file-input"
        />
        <label
          htmlFor="csv-file-input"
          className="cursor-pointer inline-flex items-center space-x-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold transition-colors"
        >
          <span>Choose File</span>
        </label>
        {file && (
          <p className="text-xs text-emerald-400 mt-3 font-mono">Selected: {file.name}</p>
        )}
      </div>

      {file && !preview && (
        <button
          onClick={handleUploadPreview}
          disabled={loading}
          className="w-full py-3 bg-sky-600 hover:bg-sky-500 text-white font-semibold text-sm rounded-xl transition-colors flex items-center justify-center space-x-2"
        >
          <span>{loading ? "Parsing CSV..." : "Parse & Preview File"}</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      )}

      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-300 text-xs rounded-xl flex items-center space-x-3">
          <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {successMsg && (
        <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs rounded-xl flex items-center space-x-3">
          <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* CSV Preview Table */}
      {preview && (
        <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-slate-100">Parsed CSV Preview</h3>
              <p className="text-xs text-slate-400">Detected {preview.valid_rows} valid holdings out of {preview.total_rows} rows.</p>
            </div>
            <div className="text-right">
              <span className="text-xs text-slate-400">Estimated Total Value</span>
              <p className="text-lg font-bold text-emerald-400">{formatCurrency(preview.estimated_total_value)}</p>
            </div>
          </div>

          <div className="overflow-x-auto max-h-96 border border-[#1e293b] rounded-lg">
            <table className="w-full text-xs text-left text-slate-300">
              <thead className="bg-[#0a0d14] text-slate-400 uppercase border-b border-[#1e293b]">
                <tr>
                  <th className="p-3">Symbol</th>
                  <th className="p-3">Name</th>
                  <th className="p-3 text-right">Quantity</th>
                  <th className="p-3 text-right">Avg Price</th>
                  <th className="p-3 text-right">Cost Basis</th>
                  <th className="p-3 text-right">Value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1e293b]">
                {preview.rows.map((row: any, idx: number) => (
                  <tr key={idx} className="hover:bg-slate-800/40">
                    <td className="p-3 font-bold text-sky-400">{row.symbol}</td>
                    <td className="p-3 text-slate-300 truncate max-w-[200px]">{row.name || "-"}</td>
                    <td className="p-3 text-right">{row.quantity || "-"}</td>
                    <td className="p-3 text-right">{row.avg_price ? formatCurrency(row.avg_price) : "-"}</td>
                    <td className="p-3 text-right">{row.cost_basis ? formatCurrency(row.cost_basis) : "-"}</td>
                    <td className="p-3 text-right font-semibold text-slate-100">
                      {formatCurrency(row.current_value)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-end space-x-4 pt-4 border-t border-[#1e293b]">
            <button
              onClick={() => setPreview(null)}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirmImport}
              disabled={confirming}
              className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg transition-colors"
            >
              {confirming ? "Importing Portfolio..." : "Confirm & Import Portfolio"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
