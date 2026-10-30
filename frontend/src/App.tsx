import { useEffect, useState } from 'react';
import { Droplets, Wheat, ShieldCheck, Activity, Layers, ArrowRight } from 'lucide-react';

interface HealthStatus {
  status: string;
}

export default function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    fetch('/api/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setHealth(data);
        setLoading(false);
      })
      .catch((err) => {
        setHealthError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-h-screen flex flex-col bg-[#081a18] text-slate-100 antialiased selection:bg-aquashift-teal selection:text-white">
      {/* Top Navigation */}
      <header className="border-b border-aquashift-deep/50 bg-[#0c2826]/80 backdrop-blur sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-aquashift-teal to-aquashift-aqua flex items-center justify-center shadow-lg shadow-aquashift-teal/20">
              <Droplets className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-extrabold text-xl tracking-tight text-white">AquaShift</span>
                <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-aquashift-deep text-aquashift-aqua border border-aquashift-teal/30">
                  Phase 0 Scaffold
                </span>
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">Zinnovatio 4.0 · AgriTech & Rural Transformation</p>
            </div>
          </div>

          {/* System Status Pill */}
          <div className="flex items-center space-x-2 text-xs px-3 py-1.5 rounded-full bg-slate-900/60 border border-slate-700/60">
            <span className="relative flex h-2 w-2">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                loading ? 'bg-amber-400' : health?.status === 'ok' ? 'bg-emerald-400' : 'bg-rose-400'
              }`} />
              <span className={`relative inline-flex rounded-full h-2 w-2 ${
                loading ? 'bg-amber-500' : health?.status === 'ok' ? 'bg-emerald-500' : 'bg-rose-500'
              }`} />
            </span>
            <span className="text-slate-300">
              API Status:{' '}
              {loading ? (
                <span className="text-amber-400 font-medium">Connecting...</span>
              ) : health?.status === 'ok' ? (
                <span className="text-emerald-400 font-medium">Online (200 OK)</span>
              ) : (
                <span className="text-rose-400 font-medium">Offline ({healthError})</span>
              )}
            </span>
          </div>
        </div>
      </header>

      {/* Hero & Branding Section */}
      <main className="flex-1 max-w-6xl mx-auto px-4 py-12 w-full space-y-12">
        <section className="text-center space-y-4 max-w-3xl mx-auto pt-4">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-aquashift-wheat/10 text-aquashift-wheat border border-aquashift-wheat/30 text-xs font-semibold tracking-wide uppercase">
            <Wheat className="w-3.5 h-3.5" />
            <span>Water-Constrained Crop Diversification Simulator</span>
          </div>
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight text-white leading-tight">
            Plan crops. <span className="text-aquashift-aqua">Balance water.</span> <span className="text-aquashift-wheat">Protect livelihoods.</span>
          </h1>
          <p className="text-base sm:text-lg text-slate-300 leading-relaxed">
            The decision layer for agriculture under competing constraints. AquaShift unites predictive machine learning,
            mathematical optimization via OR-Tools, and transparent AI explanations to navigate water scarcity.
          </p>
        </section>

        {/* Core Principles Grid */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-6 rounded-2xl bg-[#0f3633]/60 border border-aquashift-teal/30 hover:border-aquashift-teal/60 transition shadow-lg">
            <div className="w-12 h-12 rounded-xl bg-aquashift-deep/70 flex items-center justify-center text-aquashift-aqua mb-4 border border-aquashift-teal/20">
              <Activity className="w-6 h-6" />
            </div>
            <h3 className="font-bold text-lg text-white mb-2">1. ML Predicts</h3>
            <p className="text-sm text-slate-300 leading-relaxed">
              scikit-learn models estimate crop yield and seasonal water demand across climate and rainfall stress scenarios using calibrated FAO-56 functions.
            </p>
          </div>

          <div className="p-6 rounded-2xl bg-[#0f3633]/60 border border-aquashift-wheat/30 hover:border-aquashift-wheat/60 transition shadow-lg">
            <div className="w-12 h-12 rounded-xl bg-aquashift-wheatDark/40 flex items-center justify-center text-aquashift-wheat mb-4 border border-aquashift-wheat/30">
              <Layers className="w-6 h-6" />
            </div>
            <h3 className="font-bold text-lg text-white mb-2">2. Optimization Decides</h3>
            <p className="text-sm text-slate-300 leading-relaxed">
              Google OR-Tools GLOP solver allocates crop land under hard rotation limits and soft target slacks. Extreme scenarios never fail as bare "infeasible".
            </p>
          </div>

          <div className="p-6 rounded-2xl bg-[#0f3633]/60 border border-emerald-500/30 hover:border-emerald-500/60 transition shadow-lg">
            <div className="w-12 h-12 rounded-xl bg-emerald-950/60 flex items-center justify-center text-emerald-400 mb-4 border border-emerald-500/20">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <h3 className="font-bold text-lg text-white mb-2">3. AI Explains</h3>
            <p className="text-sm text-slate-300 leading-relaxed">
              Plain-language summaries verified against solver output numbers. If numeric validation fails or the API key is absent, deterministic templates ensure 100% offline uptime.
            </p>
          </div>
        </section>

        {/* Six-Stage Pipeline Preview */}
        <section className="p-6 sm:p-8 rounded-2xl bg-[#0b2422] border border-aquashift-deep/80 shadow-xl space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-aquashift-deep/60 pb-4">
            <div>
              <h2 className="text-xl font-bold text-white">Six-Stage AquaShift Pipeline</h2>
              <p className="text-xs text-slate-400">Integrated architecture connecting inputs, intelligence, and outcomes</p>
            </div>
            <span className="text-xs font-medium px-3 py-1 rounded-full bg-aquashift-deep text-slate-200 w-fit">
              Architecture Preview
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
              { step: '01', title: 'Scenario', desc: 'Land, water & targets' },
              { step: '02', title: 'ML Predictor', desc: 'Yield & stress demand' },
              { step: '03', title: 'Optimizer', desc: 'OR-Tools GLOP solve' },
              { step: '04', title: 'Stress Test', desc: 'Bottleneck diagnosis' },
              { step: '05', title: 'AI Insight', desc: 'Verified explanation' },
              { step: '06', title: 'Crop Plan', desc: 'Water, food & income' },
            ].map((item, idx) => (
              <div
                key={item.step}
                className="p-3.5 rounded-xl bg-[#081a18]/70 border border-aquashift-teal/20 flex flex-col justify-between"
              >
                <div className="flex items-center justify-between text-xs text-aquashift-aqua font-mono mb-2">
                  <span>{item.step}</span>
                  {idx < 5 && <ArrowRight className="w-3 h-3 text-slate-600 hidden lg:block" />}
                </div>
                <div>
                  <h4 className="font-semibold text-sm text-white mb-0.5">{item.title}</h4>
                  <p className="text-xs text-slate-400 leading-snug">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* Footer with mandatory Synthetic Demo Data disclosure */}
      <footer className="border-t border-aquashift-deep/50 bg-[#061413] py-8 text-xs text-slate-400 mt-auto">
        <div className="max-w-6xl mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <span className="font-bold text-slate-200">AquaShift</span>
            <span>·</span>
            <span>Team NullPointers (Zinnovatio 4.0)</span>
          </div>
          <div className="px-3.5 py-1.5 rounded-lg bg-[#0c2826] border border-aquashift-teal/30 text-aquashift-aqua text-center font-medium">
            Synthetic demo data calibrated to public agri statistics.
          </div>
          <div className="text-slate-500">
            Phase 0 Scaffold Verified
          </div>
        </div>
      </footer>
    </div>
  );
}
