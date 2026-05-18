"use client";

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createChart, CandlestickSeries, Time, CrosshairMode } from 'lightweight-charts';
import { Activity, TrendingUp, ShieldCheck, Target, Crosshair, Wallet, XCircle, BookOpen, PenTool } from 'lucide-react';

export default function Dashboard() {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const [ticks, setTicks] = useState<Record<string, any>>({});
    const [aiInsight, setAiInsight] = useState<string>("Loading real-time AI analyst insight...");
    const [chainMetrics, setChainMetrics] = useState<any>({ max_pain: 0, pcr: 0, atm_premiums: null });
    const [riskParams, setRiskParams] = useState<any>(null);
    const [strategy, setStrategy] = useState<any>(null);
    
    // Paper Trading State — persisted in localStorage (loaded after mount to avoid SSR hydration mismatch)
    const [paperAccount, setPaperAccount] = useState({ balance: 100000 });
    const [activeTrade, setActiveTrade] = useState<any>(null);
    const [realtimePnL, setRealtimePnL] = useState<number>(0);
    const [tradeHistory, setTradeHistory] = useState<any[]>([]);
    const [mounted, setMounted] = useState(false);
    const [livePremium, setLivePremium] = useState<number | null>(null);
    const livePremiumRef = useRef<number | null>(null);
    
    // ML 6-Month Backtest Training States
    const [isTraining, setIsTraining] = useState(false);
    const [trainingReport, setTrainingReport] = useState<any>(null);
    const [trainingParams, setTrainingParams] = useState<any>(null);

    // Load persisted data from Supabase backend on mount
    useEffect(() => {
        const fetchInitialData = async () => {
            try {
                // Fetch demo balance
                const balanceRes = await fetch('http://localhost:8000/api/analysis/profile');
                if (balanceRes.ok) {
                    const balanceData = await balanceRes.json();
                    setPaperAccount({ balance: balanceData.balance });
                }
                
                // Fetch trade journal history
                const tradesRes = await fetch('http://localhost:8000/api/analysis/trades');
                if (tradesRes.ok) {
                    const tradesData = await tradesRes.json();
                    setTradeHistory(tradesData);
                }
            } catch (error) {
                console.error("Failed to load initial Supabase data", error);
            }
        };

        fetchInitialData();
        setMounted(true);
    }, []);

    // Use exact expiry fetched from NSE API, fallback to a placeholder until loaded
    const nextExpiry = chainMetrics.next_expiry || "Loading...";

    // Manual Form State
    const [manualForm, setManualForm] = useState({ direction: 'CE', strike: '24800', qty: 65, target: '', sl: '' });

    // Candlestick tracking refs
    const candleDataRef = useRef<{time: Time, open: number, high: number, low: number, close: number}[]>([]);
    const candleSeriesRef = useRef<any>(null);
    const currentPriceRef = useRef<number>(24800); // Default fallback
    
    // Price Line Refs for Chart
    const entryLineRef = useRef<any>(null);
    const slLineRef = useRef<any>(null);
    const tpLineRef = useRef<any>(null);
    
    // Live price state
    const [isConnected, setIsConnected] = useState(false);
    const [liveChange, setLiveChange] = useState({ change: 0, pct: 0 });
    const [livePrice, setLivePrice] = useState<number | null>(null);
    
    // Timeframe selector (in minutes)
    const [timeframe, setTimeframe] = useState(1);
    const timeframeRef = useRef(1);
    const activeTradeRef = useRef<any>(null);
    activeTradeRef.current = activeTrade;
    const closeTradeFnRef = useRef<any>(null);

    // Poll live price from backend REST API every 2 seconds
    const updatePrice = useCallback((price: number) => {
        if (!candleSeriesRef.current) return;
        currentPriceRef.current = price;
        setLivePrice(price);

        const now = new Date();
        const tfMs = timeframeRef.current * 60 * 1000;
        const timeStr = Math.floor(Math.floor(now.getTime() / tfMs) * tfMs / 1000) as Time;

        let currentCandle = candleDataRef.current.find(c => c.time === timeStr);
        if (currentCandle) {
            currentCandle.close = price;
            currentCandle.high = Math.max(currentCandle.high, price);
            currentCandle.low = Math.min(currentCandle.low, price);
            candleSeriesRef.current.update({ ...currentCandle });
        } else {
            const prev = candleDataRef.current[candleDataRef.current.length - 1];
            const newCandle = { time: timeStr, open: prev?.close ?? price, high: price, low: price, close: price };
            candleDataRef.current.push(newCandle);
            candleSeriesRef.current.update(newCandle);
        }
        // Persist candle data (keep last 200 candles)
        try {
            const toSave = candleDataRef.current.slice(-200);
            localStorage.setItem('qt_candles', JSON.stringify(toSave));
        } catch {}

        // Paper trade P&L using refs to avoid stale closure
        const trade = activeTradeRef.current;
        if (trade && closeTradeFnRef.current) {
            const pnl = trade.direction === 'CE'
                ? (price - trade.entry) * trade.qty
                : (trade.entry - price) * trade.qty;
            const slHit = trade.direction === 'CE' ? price <= trade.sl : price >= trade.sl;
            const tpHit = trade.direction === 'CE' ? price >= trade.target : price <= trade.target;
            if (slHit || tpHit) {
                closeTradeFnRef.current(pnl, slHit ? 'SL Hit' : 'Target Hit');
            } else {
                setRealtimePnL(pnl);
            }
        }
    }, []);

    useEffect(() => {
        let alive = true;
        const poll = async () => {
            while (alive) {
                try {
                    const res = await fetch('http://localhost:8000/api/analysis/live-price');
                    if (res.ok) {
                        const data = await res.json();
                        if (data.last_price) {
                            setIsConnected(true);
                            setLiveChange({ change: data.change, pct: data.pct_change });
                            updatePrice(data.last_price);
                        }
                    }
                } catch {
                    setIsConnected(false);
                }
                await new Promise(r => setTimeout(r, 2000));
            }
        };
        poll();
        return () => { alive = false; };
    }, [updatePrice]);
    // Poll live premium every 3s when a trade is active
    useEffect(() => {
        if (!activeTrade) { setLivePremium(null); return; }
        let alive = true;
        const strike = parseInt(activeTrade.strike);
        const optType = activeTrade.direction;
        const pollPremium = async () => {
            while (alive && activeTradeRef.current) {
                try {
                    const res = await fetch(`http://localhost:8000/api/analysis/live-premium/${strike}/${optType}`);
                    if (res.ok) {
                        const data = await res.json();
                        if (data.ltp) {
                            setLivePremium(data.ltp);
                            livePremiumRef.current = data.ltp;
                            // P&L based on premium change (correct options P&L)
                            const pnl = (data.ltp - activeTradeRef.current.entryPremium) * activeTradeRef.current.qty;
                            setRealtimePnL(pnl);
                        }
                    }
                } catch {}
                await new Promise(r => setTimeout(r, 3000));
            }
        };
        pollPremium();
        return () => { alive = false; };
    }, [activeTrade]);

    const [lastUpdated, setLastUpdated] = useState<string>('');
    const [countdown, setCountdown] = useState(30);

    useEffect(() => {
        let secs = 30;
        const fetchAnalysis = async () => {
            try {
                const res = await fetch('http://localhost:8000/api/analysis/option-chain/NIFTY');
                if (res.ok) {
                    const data = await res.json();
                    setAiInsight(data.ai_insight);
                    setChainMetrics(data.chain_metrics);
                    setRiskParams(data.risk_params);
                    setStrategy(data.strategy);
                    setLastUpdated(new Date().toLocaleTimeString('en-IN'));
                    secs = 30;
                    setCountdown(30);
                }
            } catch (error) {
                console.error("Failed to fetch AI insight", error);
            }
        };

        fetchAnalysis();
        const interval = setInterval(fetchAnalysis, 30000);
        // Countdown ticker
        const ticker = setInterval(() => {
            secs = secs <= 1 ? 30 : secs - 1;
            setCountdown(secs);
        }, 1000);
        return () => { clearInterval(interval); clearInterval(ticker); };
    }, []);

    const handleTrainModel = async () => {
        setIsTraining(true);
        try {
            const res = await fetch('http://localhost:8000/api/analysis/train', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                if (data.status === 'success') {
                    setTrainingReport(data.backtest_report);
                    setTrainingParams(data.optimized_parameters);
                } else {
                    alert("Training failed: " + data.message);
                }
            }
        } catch (error) {
            console.error("Training error:", error);
            alert("Failed to connect to ML training engine.");
        } finally {
            setIsTraining(false);
        }
    };

    const executePaperTrade = () => {
        if (!strategy || strategy.signal.includes("WAIT") || strategy.signal.includes("NO TRADE")) return;
        
        const direction = strategy.signal.includes("BUY CE") ? "CE" : "PE";
        const qty = 65; // Fixed default quantity
        const atmStrike = Math.round((livePrice || strategy.entry_price) / 50) * 50;
        const currentPremium = direction === 'CE' ? chainMetrics?.atm_premiums?.ce_ltp : chainMetrics?.atm_premiums?.pe_ltp;

        setActiveTrade({
            direction,
            strike: atmStrike.toString(),
            entry: livePrice || strategy.entry_price,
            entryPremium: currentPremium || 0,
            entryTime: new Date().toLocaleTimeString(),
            sl: strategy.stop_loss,
            target: strategy.target,
            qty,
        });
        setRealtimePnL(0);
    };

    const executeManualTrade = () => {
        if (!manualForm.target || !manualForm.sl || !manualForm.strike || manualForm.qty <= 0) return;
        
        const currentPremium = manualForm.direction === 'CE' ? chainMetrics?.atm_premiums?.ce_ltp : chainMetrics?.atm_premiums?.pe_ltp;

        setActiveTrade({
            direction: manualForm.direction,
            strike: manualForm.strike,
            entry: currentPriceRef.current,
            entryPremium: currentPremium || 0,
            entryTime: new Date().toLocaleTimeString(),
            sl: parseFloat(manualForm.sl),
            target: parseFloat(manualForm.target),
            qty: manualForm.qty,
        });
        setRealtimePnL(0);
    };

    const closeTrade = async (finalPnL?: number, reason: string = 'Manual Exit') => {
        const trade = activeTradeRef.current;
        if (!trade) return;
        
        const pnl = finalPnL !== undefined ? finalPnL : realtimePnL;
        const newBalance = paperAccount.balance + pnl;
        setPaperAccount({ balance: newBalance });
        
        // Use live premium if available, fallback to chain metrics
        const currentPremium = livePremiumRef.current !== null 
            ? livePremiumRef.current 
            : (trade.direction === 'CE' ? chainMetrics?.atm_premiums?.ce_ltp : chainMetrics?.atm_premiums?.pe_ltp);
            
        const exitSpot = currentPriceRef.current;

        try {
            // 1. Update balance in Supabase
            await fetch('http://localhost:8000/api/analysis/profile/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ balance: newBalance })
            });

            // 2. Save trade to Supabase
            await fetch('http://localhost:8000/api/analysis/trades', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    direction: trade.direction,
                    strike: trade.strike,
                    qty: trade.qty,
                    entry_spot: trade.entry,
                    exit_spot: exitSpot,
                    entry_premium: trade.entryPremium,
                    exit_premium: currentPremium || 0,
                    pnl: pnl,
                    reason: reason
                })
            });

            // 3. Re-fetch fresh trade history from Supabase
            const tradesRes = await fetch('http://localhost:8000/api/analysis/trades');
            if (tradesRes.ok) {
                const tradesData = await tradesRes.json();
                setTradeHistory(tradesData);
            }
        } catch (error) {
            console.error("Failed to sync trade with Supabase", error);
        }

        setActiveTrade(null);
        setRealtimePnL(0);
        setLivePremium(null);
        livePremiumRef.current = null;
    };
    // Always keep ref in sync
    closeTradeFnRef.current = closeTrade;

    // Sync timeframe state to ref (used inside updatePrice)
    useEffect(() => { timeframeRef.current = timeframe; }, [timeframe]);


    // Draw Price Lines on Chart when Trade is Active
    useEffect(() => {
        if (!candleSeriesRef.current) return;
        
        // Remove old lines if they exist
        if (entryLineRef.current) candleSeriesRef.current.removePriceLine(entryLineRef.current);
        if (slLineRef.current) candleSeriesRef.current.removePriceLine(slLineRef.current);
        if (tpLineRef.current) candleSeriesRef.current.removePriceLine(tpLineRef.current);
        
        // Draw new lines if trade is active
        if (activeTrade) {
            entryLineRef.current = candleSeriesRef.current.createPriceLine({
                price: activeTrade.entry,
                color: '#3b82f6', // blue-500
                lineWidth: 2,
                lineStyle: 2, // dashed
                axisLabelVisible: true,
                title: 'ENTRY',
            });
            slLineRef.current = candleSeriesRef.current.createPriceLine({
                price: activeTrade.sl,
                color: '#ef4444', // red-500
                lineWidth: 2,
                lineStyle: 2,
                axisLabelVisible: true,
                title: 'SL',
            });
            tpLineRef.current = candleSeriesRef.current.createPriceLine({
                price: activeTrade.target,
                color: '#10b981', // emerald-500
                lineWidth: 2,
                lineStyle: 2,
                axisLabelVisible: true,
                title: 'TARGET',
            });
        }
    }, [activeTrade]);

    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: { 
                background: { type: 'solid', color: '#020617' }, 
                textColor: '#94a3b8' 
            },
            grid: { 
                vertLines: { color: '#0f172a', style: 1 }, 
                horzLines: { color: '#0f172a', style: 1 } 
            },
            crosshair: {
                mode: CrosshairMode.Normal,
                vertLine: { width: 1, color: '#334155', style: 3 },
                horzLine: { width: 1, color: '#334155', style: 3 },
            },
            rightPriceScale: {
                borderColor: '#1e293b',
                autoScale: true,
                scaleMargins: { top: 0.1, bottom: 0.1 },
            },
            localization: {
                timeFormatter: (time: number) => {
                    const d = new Date(time * 1000);
                    return d.toLocaleString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
                }
            },
            timeScale: { 
                borderColor: '#1e293b',
                timeVisible: true, 
                secondsVisible: false,
                tickMarkFormatter: (time: number, tickMarkType: any, locale: any) => {
                    const d = new Date(time * 1000);
                    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                },
                rightOffset: 20, // Leaves space on the right side
                barSpacing: 12,  // Makes candles thicker
            },
            width: chartContainerRef.current.clientWidth,
            height: 480,
            handleScroll: {
                mouseWheel: true,
                pressedMouseMove: true,
            },
            handleScale: {
                axisPressedMouseMove: true,
                mouseWheel: true,
                pinch: true,
            },
        });

        const candlestickSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#10b981', downColor: '#ef4444', borderVisible: false,
            wickUpColor: '#10b981', wickDownColor: '#ef4444',
        });
        
        candleSeriesRef.current = candlestickSeries;

        // Restore candle data from localStorage (today's session)
        try {
            const saved = localStorage.getItem('qt_candles');
            if (saved) {
                const parsed = JSON.parse(saved);
                // Only restore if data is from today
                const todayStart = Math.floor(new Date().setHours(9, 15, 0, 0) / 1000);
                const filtered = parsed.filter((c: any) => c.time >= todayStart);
                if (filtered.length > 0) {
                    candlestickSeries.setData(filtered);
                    candleDataRef.current = filtered;
                    chart.timeScale().scrollToRealTime();
                } else {
                    candleDataRef.current = [];
                }
            } else {
                candleDataRef.current = [];
            }
        } catch {
            candleDataRef.current = [];
        }
        chart.timeScale().fitContent();

        const handleResize = () => {
            if (chartContainerRef.current) chart.applyOptions({ width: chartContainerRef.current.clientWidth });
        };
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, []);

    return (
        <div className="min-h-screen text-slate-100 p-6 font-sans flex flex-col">
            <header className="flex justify-between items-center mb-6 pb-4 border-b border-slate-800">
                <div className="flex items-center gap-3">
                    <Activity className="text-emerald-500 w-8 h-8" />
                    <h1 className="text-2xl font-bold tracking-tight">QuantumTrade AI</h1>
                </div>
                <div className="flex gap-4">
                    <div className="bg-slate-900 px-4 py-2 rounded-lg border border-slate-800 flex items-center gap-2">
                        <Wallet className="text-blue-400 w-4 h-4" />
                        <span className="text-slate-400 text-sm font-medium">Demo Balance:</span>
                        <span className="font-mono font-bold text-white" suppressHydrationWarning>₹{paperAccount.balance.toLocaleString('en-IN')}</span>
                    </div>
                    <div className="bg-slate-900 px-4 py-2 rounded-lg border border-slate-800 flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`}></div>
                        <span className="text-slate-400 text-sm font-medium">Live Market</span>
                    </div>
                    <div className="bg-slate-900 px-4 py-2 rounded-lg border border-slate-800 flex items-center">
                        <span className="text-slate-400 text-sm">NIFTY 50</span>
                        <span className="ml-2 text-[10px] font-bold px-2 py-0.5 bg-indigo-900/40 text-indigo-300 rounded border border-indigo-800/50">
                            Exp: {nextExpiry}
                        </span>
                        <span className="ml-3 font-mono font-bold text-white text-lg">
                            {livePrice ? livePrice.toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '—'}
                        </span>
                        {livePrice && (
                            <span className={`ml-2 text-xs font-mono font-bold ${
                                liveChange.change >= 0 ? 'text-emerald-400' : 'text-red-400'
                            }`}>
                                {liveChange.change >= 0 ? '+' : ''}{liveChange.change.toFixed(2)} ({liveChange.pct.toFixed(2)}%)
                            </span>
                        )}
                    </div>
                    {chainMetrics.atm_premiums && (
                        <div className="bg-slate-900 px-3 py-2 rounded-lg border border-slate-800 flex items-center gap-3">
                            <span className="text-slate-400 text-xs font-bold">ATM ({chainMetrics.atm_premiums.strike})</span>
                            <div className="flex items-center gap-2 border-l border-slate-700 pl-3">
                                <span className={`text-xs font-mono font-bold ${chainMetrics.atm_premiums.ce_change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                    CE ₹{chainMetrics.atm_premiums.ce_ltp} ({chainMetrics.atm_premiums.ce_change > 0 ? '+' : ''}{chainMetrics.atm_premiums.ce_change}%)
                                </span>
                                <span className="text-slate-600">|</span>
                                <span className={`text-xs font-mono font-bold ${chainMetrics.atm_premiums.pe_change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                    PE ₹{chainMetrics.atm_premiums.pe_ltp} ({chainMetrics.atm_premiums.pe_change > 0 ? '+' : ''}{chainMetrics.atm_premiums.pe_change}%)
                                </span>
                            </div>
                        </div>
                    )}
                </div>
            </header>

            <div className="grid grid-cols-12 gap-6 flex-1">
                {/* Main Content Area */}
                <div className="col-span-8 flex flex-col gap-6">
                    {/* Chart */}
                    <div className="bg-slate-900 rounded-xl border border-slate-800 p-5 shadow-lg">
                        <div className="flex justify-between items-center mb-4">
                            <h2 className="text-lg font-semibold text-slate-200">Advanced Price Action</h2>
                            {/* Timeframe Selector */}
                            <div className="flex gap-1 bg-slate-950 rounded-lg p-1 border border-slate-800">
                                {[1, 3, 5, 15].map(tf => (
                                    <button
                                        key={tf}
                                        onClick={() => setTimeframe(tf)}
                                        className={`px-3 py-1 rounded text-xs font-bold transition-all ${
                                            timeframe === tf
                                                ? 'bg-indigo-600 text-white shadow'
                                                : 'text-slate-400 hover:text-white'
                                        }`}
                                    >
                                        {tf}M
                                    </button>
                                ))}
                            </div>
                        </div>
                        <div ref={chartContainerRef} className="w-full rounded overflow-hidden" style={{ height: '480px', minHeight: '480px' }} />
                    </div>

                    {/* Paper Trading Panel */}
                    <div className="bg-slate-900 rounded-xl border border-slate-800 p-5 shadow-lg flex-1">
                        <h2 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
                            <PenTool className="w-5 h-5 text-blue-400" />
                            Live Paper Trading Desk
                        </h2>
                                       {activeTrade ? (
                            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                                <div className="flex justify-between items-center mb-3">
                                    <div>
                                        <span className={`font-bold text-lg ${activeTrade.direction === 'CE' ? 'text-emerald-400' : 'text-red-400'}`}>
                                            BUY {activeTrade.strike} {activeTrade.direction}
                                        </span>
                                        <span className="text-slate-500 text-xs ml-2">Qty: {activeTrade.qty} | Entry: {activeTrade.entryTime}</span>
                                    </div>
                                    <button onClick={() => closeTrade()} className="text-xs flex items-center gap-1 text-slate-400 hover:text-red-400 transition-colors">
                                        <XCircle className="w-4 h-4" /> Exit
                                    </button>
                                </div>
                                <div className="grid grid-cols-4 gap-3">
                                    <div className="bg-slate-900 p-3 rounded border border-slate-800">
                                        <div className="text-xs text-slate-500 mb-1">Entry Premium</div>
                                        <div className="font-mono font-bold text-blue-400">₹{activeTrade.entryPremium?.toFixed(2) || '—'}</div>
                                    </div>
                                    <div className="bg-slate-900 p-3 rounded border border-slate-800">
                                        <div className="text-xs text-slate-500 mb-1">Live Premium</div>
                                        <div className={`font-mono font-bold ${livePremium && livePremium > (activeTrade.entryPremium || 0) ? 'text-emerald-400' : 'text-red-400'}`}>
                                            {livePremium ? `₹${livePremium.toFixed(2)}` : 'Fetching...'}
                                        </div>
                                    </div>
                                    <div className="bg-slate-900 p-3 rounded border border-slate-800">
                                        <div className="text-xs text-slate-500 mb-1">Spot / SL / Tgt</div>
                                        <div className="font-mono text-xs">
                                            <span className="text-white">{livePrice?.toFixed(0)}</span>
                                            <span className="text-red-400 mx-1">/{activeTrade.sl}</span>
                                            <span className="text-emerald-400">/{activeTrade.target}</span>
                                        </div>
                                    </div>
                                    <div className="bg-slate-900 p-3 rounded border border-slate-800 text-right">
                                        <div className="text-xs text-slate-500 mb-1">Live P&L</div>
                                        <div className={`font-mono text-xl font-bold ${realtimePnL >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                            {realtimePnL >= 0 ? '+' : '-'}₹{Math.abs(realtimePnL).toFixed(0)}
                                        </div>
                                        {livePremium && <div className="text-xs text-slate-600 mt-0.5">
                                            Premium Δ: {livePremium > (activeTrade.entryPremium||0) ? '+' : ''}{(livePremium - (activeTrade.entryPremium||0)).toFixed(2)}
                                        </div>}
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                                <h3 className="text-sm font-semibold text-slate-400 mb-3">Manual Trade Execution</h3>
                                <div className="grid grid-cols-5 gap-4">
                                    <div>
                                        <label className="text-xs text-slate-500 block mb-1">Direction</label>
                                        <select 
                                            value={manualForm.direction} 
                                            onChange={e => setManualForm({...manualForm, direction: e.target.value})}
                                            className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-white"
                                        >
                                            <option value="CE">BUY CE (Call)</option>
                                            <option value="PE">BUY PE (Put)</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="text-xs text-slate-500 block mb-1">Quantity</label>
                                        <input 
                                            type="number" value={manualForm.qty} 
                                            onChange={e => setManualForm({...manualForm, qty: Number(e.target.value)})}
                                            className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-white"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs text-slate-500 block mb-1">Strike</label>
                                        <input 
                                            type="text" placeholder="e.g. 24800" value={manualForm.strike} 
                                            onChange={e => setManualForm({...manualForm, strike: e.target.value})}
                                            className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-white"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs text-slate-500 block mb-1">Target Price</label>
                                        <input 
                                            type="number" placeholder="25000" value={manualForm.target} 
                                            onChange={e => setManualForm({...manualForm, target: e.target.value})}
                                            className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-emerald-400 font-mono"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs text-slate-500 block mb-1">Stop Loss</label>
                                        <input 
                                            type="number" placeholder="24700" value={manualForm.sl} 
                                            onChange={e => setManualForm({...manualForm, sl: e.target.value})}
                                            className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-red-400 font-mono"
                                        />
                                    </div>
                                    <div className="flex items-end">
                                        <button 
                                            onClick={executeManualTrade}
                                            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 rounded transition-colors"
                                        >
                                            Place Trade
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Trade History (Journal) */}
                    <div className="bg-slate-900 rounded-xl border border-slate-800 p-5 shadow-lg">
                        <h2 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
                            <BookOpen className="w-5 h-5 text-purple-400" />
                            Trade Journal (History)
                            {tradeHistory.length > 0 && (
                                <button onClick={() => { setTradeHistory([]); localStorage.removeItem('qt_journal'); }}
                                    className="ml-auto text-xs text-slate-500 hover:text-red-400 transition-colors">
                                    Clear All
                                </button>
                            )}
                        </h2>
                        {tradeHistory.length > 0 ? (
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm text-left text-slate-400">
                                    <thead className="text-xs text-slate-500 uppercase bg-slate-950/50">
                                        <tr>
                                            <th className="px-4 py-2 rounded-tl-lg">Time (Entry → Exit)</th>
                                            <th className="px-4 py-2">Position</th>
                                            <th className="px-4 py-2">Spot (Entry → Exit)</th>
                                            <th className="px-4 py-2">Premium (Entry → Exit)</th>
                                            <th className="px-4 py-2">Reason</th>
                                            <th className="px-4 py-2 rounded-tr-lg text-right">P&L</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {tradeHistory.map((trade, i) => (
                                            <tr key={i} className="border-b border-slate-800/50 last:border-0 hover:bg-slate-800/20">
                                                <td className="px-4 py-3 whitespace-nowrap">
                                                    <span className="text-slate-300">{trade.entryTime}</span>
                                                    <span className="text-slate-600 mx-1">→</span>
                                                    <span className="text-slate-400">{trade.exitTime}</span>
                                                </td>
                                                <td className="px-4 py-3 font-bold">{trade.strike} {trade.direction} ({trade.qty})</td>
                                                <td className="px-4 py-3 font-mono">
                                                    <span className="text-slate-300">{trade.entry}</span>
                                                    <span className="text-slate-600 mx-1">→</span>
                                                    <span className="text-slate-400">{trade.exitPrice}</span>
                                                </td>
                                                <td className="px-4 py-3 font-mono">
                                                    <span className="text-blue-400">₹{trade.entryPremium}</span>
                                                    <span className="text-slate-600 mx-1">→</span>
                                                    <span className="text-blue-300">₹{trade.exitPremium}</span>
                                                </td>
                                                <td className="px-4 py-3 text-xs">{trade.reason}</td>
                                                <td className={`px-4 py-3 font-mono font-bold text-right ${trade.pnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                                    {trade.pnl >= 0 ? '+' : '-'}₹{Math.abs(trade.pnl).toFixed(2)}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <div className="text-center p-6 text-slate-500 italic bg-slate-950 rounded-lg border border-slate-800 border-dashed">
                                No trades executed yet. Your closed trades will appear here.
                            </div>
                        )}
                    </div>
                </div>

                {/* Sidebar */}
                <div className="col-span-4 flex flex-col gap-6">
                    {/* AI Insights Panel */}
                    <div className="bg-slate-900 rounded-xl border border-slate-800 p-5 shadow-lg">
                        <h2 className="text-lg font-semibold mb-1 text-slate-200 flex items-center gap-2">
                            <ShieldCheck className="w-5 h-5 text-blue-400" />
                            AI Analyst Insights
                            <span className="ml-auto flex items-center gap-2">
                                <span className="text-xs text-slate-600 font-normal">
                                    {lastUpdated ? `Updated: ${lastUpdated}` : 'Loading...'}
                                </span>
                                <span className="text-[10px] font-mono bg-slate-800 text-indigo-400 px-2 py-0.5 rounded border border-slate-700">
                                    🔄 {countdown}s
                                </span>
                            </span>
                        </h2>
                        <div className="space-y-4 mt-3">
                            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 border-l-4 border-l-emerald-500">
                                <p className="text-sm text-slate-300 leading-relaxed font-mono">
                                    {aiInsight}
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Golden Setup Strategy Engine */}
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 flex-1">
                        <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2 mb-4">
                            <Target className="w-5 h-5 text-emerald-400" />
                            Golden Setup (Live Signal)
                        </h2>

                        <div className="space-y-4 mb-6">
                            {strategy ? (
                                <>
                                    <div className={`p-4 rounded-lg font-bold text-center text-xl border ${strategy.signal.includes('BUY') ? 'bg-emerald-900/30 border-emerald-500 text-emerald-400' : 'bg-slate-900 border-slate-700 text-slate-400'}`}>
                                        {strategy.signal}
                                    </div>
                                    <div className="grid grid-cols-2 gap-3 mt-4">
                                        <div className="bg-slate-950 p-3 rounded border border-slate-800">
                                            <div className="text-xs text-slate-500 mb-1">Resistance</div>
                                            <div className="font-mono text-md text-red-400">{strategy.resistance}</div>
                                        </div>
                                        <div className="bg-slate-950 p-3 rounded border border-slate-800">
                                            <div className="text-xs text-slate-500 mb-1">Support</div>
                                            <div className="font-mono text-md text-emerald-400">{strategy.support}</div>
                                        </div>
                                    </div>

                                    {/* Real-time Indicator Metrics (Step 1 & Step 2) */}
                                    <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 mt-4 space-y-3">
                                        <div className="text-xs font-bold uppercase text-indigo-400 tracking-wider flex items-center gap-1.5">
                                            <Activity className="w-3.5 h-3.5" /> Live Technical Metrics
                                        </div>
                                        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                                            <div className="flex justify-between border-b border-slate-800/80 pb-1.5">
                                                <span className="text-slate-500 font-medium">15m Trend</span>
                                                <span className={`font-bold ${
                                                    strategy.trend_15m?.includes('BULL') ? 'text-emerald-400' : strategy.trend_15m?.includes('BEAR') ? 'text-red-400' : 'text-slate-400'
                                                }`}>{strategy.trend_15m || 'NEUTRAL'}</span>
                                            </div>
                                            <div className="flex justify-between border-b border-slate-800/80 pb-1.5">
                                                <span className="text-slate-500 font-medium">1m RSI</span>
                                                <span className="font-mono font-semibold text-slate-200">{strategy.rsi || '50'}</span>
                                            </div>
                                            <div className="flex justify-between border-b border-slate-800/80 pb-1.5">
                                                <span className="text-slate-500 font-medium">5m RSI (Dip)</span>
                                                <span className={`font-mono font-semibold ${
                                                    strategy.rsi_5m <= 38 ? 'text-emerald-400 font-bold' : strategy.rsi_5m >= 62 ? 'text-red-400 font-bold' : 'text-slate-200'
                                                }`}>{strategy.rsi_5m || '50'}</span>
                                            </div>
                                            <div className="flex justify-between border-b border-slate-800/80 pb-1.5">
                                                <span className="text-slate-500 font-medium">Session VWAP</span>
                                                <span className="font-mono text-slate-200">₹{strategy.vwap ? Math.round(strategy.vwap) : '—'}</span>
                                            </div>
                                        </div>
                                    </div>
                                    {strategy.signal.includes('BUY') && (
                                        <div className="mt-4 p-4 border border-emerald-900 bg-emerald-950/30 rounded-lg">
                                            <div className="text-sm text-slate-300 mb-3 flex items-center gap-2"><Crosshair className="w-4 h-4 text-emerald-500"/> Trade Execution Plan:</div>
                                            {/* Position Row */}
                                            <div className="flex justify-between items-center text-sm mb-2">
                                                <span className="text-slate-400">Position</span>
                                                <span className={`font-bold text-base px-3 py-0.5 rounded ${strategy.signal.includes('BUY CE') ? 'bg-emerald-900/50 text-emerald-300 border border-emerald-700' : 'bg-red-900/50 text-red-300 border border-red-700'}`}>
                                                    BUY {Math.round((livePrice || strategy.entry_price) / 50) * 50} {strategy.signal.includes('BUY CE') ? 'CE' : 'PE'}
                                                </span>
                                            </div>
                                            <div className="flex justify-between items-center text-sm mb-2">
                                                <span className="text-slate-400">Qty (Lots)</span>
                                                <span className="text-slate-200 font-bold">65 (1 lot)</span>
                                            </div>
                                            <div className="border-t border-slate-800 my-2"></div>
                                            <div className="flex justify-between items-center text-sm mb-2">
                                                <span className="text-slate-400">Entry At (LTP)</span>
                                                <span className="text-slate-200 font-bold">{livePrice ? livePrice.toFixed(2) : strategy.entry_price}</span>
                                            </div>
                                            <div className="flex justify-between items-center text-sm mb-2">
                                                <span className="text-slate-400">Stop Loss</span>
                                                <span className="text-red-400 font-bold">{strategy.stop_loss}</span>
                                            </div>
                                            <div className="flex justify-between items-center text-sm mb-2">
                                                <span className="text-slate-400">Target</span>
                                                <span className="text-emerald-400 font-bold">{strategy.target}</span>
                                            </div>
                                        </div>
                                    )}
                                </>
                            ) : (
                                <div className="text-slate-500 text-sm italic">Loading Strategy Parameters...</div>
                            )}
                        </div>

                        <button 
                            onClick={executePaperTrade}
                            disabled={!strategy || strategy.signal.includes("WAIT") || activeTrade !== null}
                            className={`w-full font-bold py-3 rounded-lg transition-colors flex justify-center items-center gap-2 shadow-lg 
                                ${(!strategy || strategy.signal.includes("WAIT") || activeTrade !== null)
                                    ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
                                    : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-900/20'}`}
                        >
                            {activeTrade ? 'Trade Active' : 'Auto-Execute Setup'}
                        </button>
                    </div>

                    {/* ML Training & Backtest Engine Card */}
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col">
                        <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2 mb-3">
                            <TrendingUp className="w-5 h-5 text-indigo-400" />
                            6-Month ML Training Engine
                        </h2>
                        <p className="text-xs text-slate-400 leading-relaxed mb-4">
                            Train the algorithmic models over the past 6 months of actual historical Nifty 50 ticks to find the mathematically optimum win-rate rules.
                        </p>
                        
                        {trainingReport ? (
                            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 text-xs space-y-2 mb-4">
                                <div className="text-indigo-400 font-bold uppercase tracking-wider mb-2">Optimal 6-Month Backtest Report</div>
                                <div className="flex justify-between border-b border-slate-900 pb-1">
                                    <span className="text-slate-500">Points Gained</span>
                                    <span className="font-mono text-emerald-400 font-bold">+{trainingReport.net_points_gained} pts</span>
                                </div>
                                <div className="flex justify-between border-b border-slate-900 pb-1">
                                    <span className="text-slate-500">Win Rate</span>
                                    <span className="font-mono text-white font-bold">{trainingReport.win_rate_pct}%</span>
                                </div>
                                <div className="flex justify-between border-b border-slate-900 pb-1">
                                    <span className="text-slate-500">Profitable Trades</span>
                                    <span className="font-mono text-emerald-400 font-bold">{trainingReport.profitable_trades} wins</span>
                                </div>
                                <div className="flex justify-between border-b border-slate-900 pb-1">
                                    <span className="text-slate-500">Total Simulated Trades</span>
                                    <span className="font-mono text-slate-300">{trainingReport.total_trades_taken}</span>
                                </div>
                                {trainingParams && <div className="text-[10px] text-indigo-300 italic pt-1.5 border-t border-slate-800">
                                    Rules optimized: RSI Bullish threshold set to {trainingParams.rsi_bullish_threshold}, Bearish to {trainingParams.rsi_bearish_threshold}!
                                </div>}
                            </div>
                        ) : null}

                        <button 
                            onClick={handleTrainModel}
                            disabled={isTraining}
                            className={`w-full font-bold py-2.5 rounded-lg transition-colors flex justify-center items-center gap-2 shadow-lg 
                                ${isTraining 
                                    ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
                                    : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-900/10'}`}
                        >
                            {isTraining ? 'Training Models... (6 Months Data)' : 'Start 6-Month ML Training'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
