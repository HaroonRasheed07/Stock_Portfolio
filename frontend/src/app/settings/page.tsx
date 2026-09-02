"use client";

import { useEffect, useState } from "react";
import { fetchAPI } from "@/lib/api";
import { Settings, Save, Shield } from "lucide-react";

export default function SettingsPage() {
  const [settings, setSettings] = useState<any>({ risk_profile: "moderate", theme: "dark" });
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState(false);

  useEffect(() => {
    fetchAPI<any>("/settings")
      .then((data) => setSettings(data))
      .catch((err) => console.error(err));
  }, []);

  const handleSave = async () => {
    try {
      setSaving(true);
      await fetchAPI("/settings", {
        method: "PUT",
        body: JSON.stringify(settings),
      });
      setSavedMsg(true);
      setTimeout(() => setSavedMsg(false), 3000);
    } catch (err: any) {
      alert("Failed to save settings: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-8 max-w-3xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Application Settings</h1>
        <p className="text-xs text-slate-400 mt-1">Configure investment preferences, risk tolerance, and local providers</p>
      </div>

      <div className="bg-[#121824] border border-[#1e293b] rounded-xl p-6 space-y-6">
        <div>
          <label className="block text-xs font-bold text-slate-300 uppercase mb-2">Investor Risk Profile</label>
          <p className="text-xs text-slate-400 mb-3">Directly influences recommendation weighting and alert sensitivity</p>
          <select
            value={settings.risk_profile || "moderate"}
            onChange={(e) => setSettings({ ...settings, risk_profile: e.target.value })}
            className="w-full bg-[#0a0d14] border border-[#1e293b] rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500/50"
          >
            <option value="conservative">Conservative (High Fundamental & Risk Weighting)</option>
            <option value="moderate">Moderate (Balanced Multi-Factor Weighting)</option>
            <option value="aggressive">Aggressive (High Momentum & Technical Weighting)</option>
          </select>
        </div>

        <div className="pt-4 border-t border-[#1e293b] flex items-center justify-between">
          {savedMsg && <span className="text-xs text-emerald-400 font-semibold">Settings saved successfully!</span>}
          <button
            onClick={handleSave}
            disabled={saving}
            className="ml-auto px-5 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold flex items-center space-x-2 transition-colors"
          >
            <Save className="w-3.5 h-3.5" />
            <span>{saving ? "Saving..." : "Save Settings"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
