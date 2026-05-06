import { useState, useEffect, useRef } from 'react';
import { Search, Loader2, CheckCircle2, AlertCircle, PlayCircle, Activity } from 'lucide-react';
import Mermaid from './components/Mermaid';

interface ILog {
  node: string;
  logs: string[];
}

interface IFinalResult {
  strategy: string;
  verification: string;
}

const MERMAID_CHART = `graph TD
    START(((START)))
    END(((END)))
    
    researcher["trend_researcher"]
    detector["anomaly_detector"]
    strategist["market_strategist"]
    verifier["verification"]

    START --> researcher
    researcher --> detector
    detector --> strategist
    strategist -->|Refine| researcher
    strategist --> verifier
    verifier --> END

    classDef active fill:#f97316,stroke:#ea580c,stroke-width:4px,color:#fff;
`;

function App() {
  const [keyword, setKeyword] = useState('');
  const [logs, setLogs] = useState<ILog[]>([]);
  const [result, setResult] = useState<IFinalResult | null>(null);
  const [status, setStatus] = useState<'idle' | 'running' | 'completed' | 'error'>('idle');
  const [currentNode, setCurrentNode] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState('');
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const runResearch = () => {
    if (!keyword.trim()) return;

    setLogs([]);
    setResult(null);
    setStatus('running');
    setCurrentNode(null);
    setErrorMessage('');

    const eventSource = new EventSource(`http://localhost:8000/research?keyword=${encodeURIComponent(keyword)}`);

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.status === 'running') {
        setCurrentNode(data.node);
        if (data.logs && data.logs.length > 0) {
          setLogs((prev) => [...prev, { node: data.node, logs: data.logs }]);
        }
        if (data.final_result) {
          setResult(data.final_result);
        }
      } else if (data.status === 'completed') {
        setStatus('completed');
        setCurrentNode(null);
        eventSource.close();
      } else if (data.status === 'error') {
        setStatus('error');
        setErrorMessage(data.message);
        eventSource.close();
      }
    };

    eventSource.onerror = () => {
      setStatus('error');
      setErrorMessage('Соединение с сервером потеряно.');
      eventSource.close();
    };
  };

  const getActiveChart = () => {
    if (!currentNode) return MERMAID_CHART;
    return `${MERMAID_CHART}\n    class ${currentNode} active;`;
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 p-8 font-sans">
      <header className="max-w-6xl mx-auto mb-12">
        <h1 className="text-4xl font-bold text-slate-800 flex items-center gap-3">
          <Activity className="text-orange-500" size={36} />
          Агент по поиску ниш
        </h1>
        <p className="text-slate-500 mt-2">Автономное исследование рынка на базе LangGraph</p>
      </header>

      <main className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left Column: Input and Logs */}
        <section className="space-y-6">
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
            <div className="flex gap-3">
              <input
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="Введите нишу (например, ИИ для вертикальных ферм)"
                className="flex-1 px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-orange-500 transition-all"
                onKeyDown={(e) => e.key === 'Enter' && runResearch()}
                disabled={status === 'running'}
              />
              <button
                onClick={runResearch}
                disabled={status === 'running' || !keyword.trim()}
                className="bg-orange-500 hover:bg-orange-600 disabled:bg-slate-300 text-white px-6 py-3 rounded-xl font-semibold flex items-center gap-2 transition-all shadow-md active:scale-95"
              >
                {status === 'running' ? <Loader2 className="animate-spin" /> : <Search size={20} />}
                {status === 'running' ? 'Исследование...' : 'Начать'}
              </button>
            </div>
          </div>

          <div className="bg-slate-900 text-slate-300 p-6 rounded-2xl shadow-inner min-h-[400px] max-h-[500px] overflow-y-auto font-mono text-sm border-4 border-slate-800">
            <h3 className="text-slate-500 mb-4 flex items-center gap-2 uppercase tracking-widest text-xs font-bold">
              <PlayCircle size={14} /> Журнал выполнения агента
            </h3>
            <div className="space-y-4">
              {logs.map((log, i) => (
                <div key={i} className="animate-in fade-in slide-in-from-left-2 duration-300">
                  <span className="text-orange-400 font-bold">[{log.node}]</span>
                  {log.logs.map((l, j) => (
                    <p key={j} className="ml-4 border-l border-slate-700 pl-3 py-1 mt-1">{l}</p>
                  ))}
                </div>
              ))}
              {status === 'running' && (
                <div className="flex items-center gap-2 text-orange-400 animate-pulse">
                  <Loader2 size={14} className="animate-spin" />
                  <span>Агент думает...</span>
                </div>
              )}
              {status === 'completed' && (
                <div className="text-green-400 flex items-center gap-2 font-bold py-2">
                  <CheckCircle2 size={16} /> Рабочий процесс завершен.
                </div>
              )}
              {status === 'error' && (
                <div className="text-red-400 flex items-center gap-2 font-bold py-2">
                  <AlertCircle size={16} /> Ошибка: {errorMessage}
                </div>
              )}
              <div ref={logEndRef} />
            </div>
          </div>
        </section>

        {/* Right Column: Visualization and Results */}
        <section className="space-y-6">
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <h3 className="text-slate-500 mb-6 flex items-center gap-2 uppercase tracking-widest text-xs font-bold">
              Визуализация графа
            </h3>
            <div className="flex justify-center p-4 bg-slate-50 rounded-xl">
               <Mermaid chart={getActiveChart()} />
            </div>
          </div>

          {result && (
            <div className="bg-white p-8 rounded-2xl shadow-lg border-2 border-orange-100 animate-in zoom-in-95 duration-500">
              <h2 className="text-2xl font-bold text-slate-800 mb-6 flex items-center gap-3">
                <CheckCircle2 className="text-green-500" />
                Стратегический анализ
              </h2>
              
              <div className="space-y-6">
                <div>
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Рыночная стратегия</h4>
                  <p className="text-slate-700 leading-relaxed bg-slate-50 p-4 rounded-xl border border-slate-100">
                    {result.strategy}
                  </p>
                </div>
                
                <div>
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Результат проверки</h4>
                  <div className="bg-green-50 text-green-800 p-4 rounded-xl border border-green-100 font-medium">
                    {result.verification}
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
