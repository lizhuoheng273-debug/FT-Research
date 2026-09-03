import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Swords, Play, Square, Save, CheckCircle2, Circle, AlertTriangle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import { debateStream, type DebateStage } from "@/lib/agents";
import { addNote } from "@/lib/notes";
import { ApiError } from "@/lib/api";
import { StockSearchInput } from "@/components/stock/StockSearchInput";

interface StageBox {
  stage: DebateStage;
  label: string;
  content: string;
  done: boolean;
  failed?: boolean;
}

// 多方用品牌橙、空方用蓝灰、主持用中性——刻意不用红绿，
// 免得和 A 股「红涨绿跌」撞车被读成涨跌信号。
const STAGE_TONE: Record<DebateStage, string> = {
  bull: "border-primary/50 bg-primary/[0.06]",
  bull_rebut: "border-primary/30 bg-primary/[0.03]",
  bear: "border-sky-500/40 bg-sky-500/[0.06]",
  bear_rebut: "border-sky-500/25 bg-sky-500/[0.03]",
  referee: "border-border bg-background/40",
};

const DOSSIER_HINT = "多空共用同一份数据底稿；来源可能延迟或缺失，观点仍需核实。";

export function Debate() {
  const [code, setCode] = useState("");
  const [stockName, setStockName] = useState("");
  const [rounds, setRounds] = useState(1);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState<{ title: string; ok: boolean }[]>([]);
  const [missing, setMissing] = useState<string[]>([]);
  const [stages, setStages] = useState<StageBox[]>([]);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [completed, setCompleted] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => () => { abortRef.current?.abort(); abortRef.current = null; }, []);

  const reset = () => {
    setStatus(""); setProgress([]); setMissing([]); setStages([]); setError(""); setSaved(false);
    setCompleted(false);
  };

  function changeCode(value: string) {
    if (abortRef.current) return;
    setCode(value); setStockName(""); reset();
  }

  async function start(requestedCode = code) {
    if (abortRef.current) return;
    const c = requestedCode.trim();
    setCode(c);
    if (!/^\d{6}$/.test(c)) { setError("请选择股票名称候选，或输入完整 6 位 A 股代码"); return; }
    reset();
    setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const active = () => abortRef.current === ctrl && !ctrl.signal.aborted;
    let failed = false;
    const finishedStages = new Set<DebateStage>();
    try {
      await debateStream(c, rounds, {
        onStatus: (message) => { if (active()) setStatus(message); },
        onDossierProgress: (title, ok, loaded, total) => {
          if (!active()) return;
          setStatus(`正在拉取客观事实底稿… ${loaded}/${total}`);
          setProgress((p) => [...p, { title, ok }]);
        },
        onDossierReady: (_sections, miss) => { if (active()) { setMissing(miss); setStatus("底稿就绪，辩论开始"); } },
        onStageStart: (stage, label) => { if (active()) setStages((s) => [...s, { stage, label, content: "", done: false }]); },
        onDelta: (stage, text) => { if (active()) setStages((s) => s.map((b) => (b.stage === stage && !b.done ? { ...b, content: b.content + text } : b))); },
        onStageDone: (stage, _label, content, stageFailed) => {
          if (!active()) return;
          failed ||= !!stageFailed || !content.trim();
          finishedStages.add(stage);
          setStages((s) => s.map((b) => (b.stage === stage && !b.done ? { ...b, content, done: true, failed: stageFailed } : b)));
        },
        onError: (message) => { if (active()) { failed = true; setError(message); } },
      }, ctrl.signal);
      if (active()) {
        const expected: DebateStage[] = rounds === 2 ? ["bull", "bear", "bull_rebut", "bear_rebut", "referee"] : ["bull", "bear", "referee"];
        const complete = !failed && expected.every((stage) => finishedStages.has(stage));
        setCompleted(complete);
        setStatus(complete ? "辩论完成" : "本轮有缺失或失败内容，未形成完整结果");
      }
    } catch (e) {
      if (!active()) return;
      setError(e instanceof ApiError ? e.message : String(e));
      setStatus("辩论未完成，请检查后重试");
    } finally {
      if (abortRef.current === ctrl) { setRunning(false); abortRef.current = null; }
    }
  }

  function stop() {
    abortRef.current?.abort();
    abortRef.current = null;
    setRunning(false);
    setCompleted(false);
    setStatus("已中止，已生成内容仅供阅读；后续角色不会继续启动");
  }

  function save() {
    if (!finished || running || saved) return;
    const body = stages.map((s) => `## ${s.label}\n\n${s.content}`).join("\n\n---\n\n");
    addNote("多空辩论", `多空辩论 · ${code.trim()}`, body);
    setSaved(true);
  }

  const finished = completed && stages.length >= 3 && stages.every((s) => s.done && !s.failed);

  return (
    <div>
      <PageHeader
        title="多空辩论"
        subtitle="同一份客观数据，多方与空方各自立论、互相质疑，最后由中立主持归纳分歧点与验证清单——不给买卖结论，判断留给你自己。"
      />

      <GlassCard>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">股票名称 / 代码</label>
            <StockSearchInput
              value={code}
              onChange={changeCode}
              onSelect={(result) => { if (!abortRef.current) { changeCode(result.code); setStockName(result.name); } }}
              onSubmitCode={(value) => { if (!running) void start(value); }}
              placeholder="输入名称或代码，如 贵州茅台 / 600519"
              disabled={running}
              className="w-72 max-w-full focus:border-sky-500"
            />
            {stockName && <p className="mt-1 text-xs text-muted-foreground">{stockName} · {code}</p>}
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">辩论深度</label>
            <select
              value={rounds}
              onChange={(e) => setRounds(Number(e.target.value))}
              disabled={running}
              className="rounded-lg border border-border/60 bg-input px-3 py-2 text-sm text-input-foreground outline-none focus:border-primary/60"
            >
              <option value={1}>一轮 · 各自陈述</option>
              <option value={2}>两轮 · 加交叉反驳</option>
            </select>
          </div>
          {running ? (
            <button onClick={stop}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border/60 px-4 py-2 text-sm hover:text-destructive">
              <Square className="h-4 w-4" /> 中止
            </button>
          ) : (
            <button onClick={() => void start()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary/90 px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary">
              <Play className="h-4 w-4" /> 开始辩论
            </button>
          )}
          {finished && !running && (
            <button onClick={save} disabled={saved}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border/60 px-4 py-2 text-sm text-muted-foreground hover:text-foreground disabled:opacity-50">
              <Save className="h-4 w-4" /> {saved ? "已保存" : "保存完整结果"}
            </button>
          )}
        </div>
        <Link to="/notes" className="mt-3 inline-block text-xs text-primary hover:underline">查看已保存记录</Link>

        {/* 开销提示：辩论比问答重得多，让用户在点下去之前就知道要花多久、调几次模型 */}
        {!running && !status && (
          <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground/70">
            ⏱ {rounds === 2
              ? "两轮 · 5 次模型调用（含交叉反驳）"
              : "一轮 · 3 次模型调用（多方、空方、中立主持）"}
            。使用后台已配置的 GLM；每个角色携带同一份底稿，会比普通问答消耗更多 Token。取数速度取决于公开数据源。
          </p>
        )}

        {status && <p role="status" className="mt-3 text-xs text-muted-foreground">{status}</p>}
        {error && (
          <p role="alert" className="mt-3 flex items-start gap-1.5 text-xs text-destructive">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {error}
          </p>
        )}

        {progress.length > 0 && (
          <div className="mt-4 border-t border-border/40 pt-3">
            <p className="mb-2 text-[11px] text-muted-foreground">{DOSSIER_HINT}</p>
            <div className="flex flex-wrap gap-x-4 gap-y-1.5">
              {progress.map((p) => (
                <span key={p.title} className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                  {p.ok
                    ? <CheckCircle2 className="h-3 w-3 text-primary/70" />
                    : <Circle className="h-3 w-3 text-muted-foreground/40" />}
                  {p.title}
                </span>
              ))}
            </div>
            {missing.length > 0 && (
              <p className="mt-2 text-[11px] text-warning">
                未取到：{missing.join("、")}（双方立论时不得臆测这部分）
              </p>
            )}
          </div>
        )}
      </GlassCard>

      <div className="mt-4 space-y-4">
        {stages.map((s) => (
          <div key={s.stage} className={`rounded-xl border p-4 ${STAGE_TONE[s.stage]}`}>
            <div className="mb-2 flex items-center gap-2">
              <Swords className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-semibold">{s.label}</span>
              {!s.done && <span className="text-[11px] text-muted-foreground">{running ? "生成中…" : "未完成"}</span>}
              {s.failed && <span className="text-[11px] text-destructive">生成失败</span>}
            </div>
            <div className="prose prose-sm dark:prose-invert max-w-none text-foreground prose-table:text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.content || "…"}</ReactMarkdown>
            </div>
          </div>
        ))}
      </div>

      {stages.length === 0 && !running && (
        <GlassCard className="mt-4">
          <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
            <Swords className="h-8 w-8 text-muted-foreground/40" />
            选择股票后开始。后端会先拉取数据底稿，再由多方、空方和中立主持依次流式输出。
            <span className="text-xs">产出的是「分歧点 + 验证清单」，不是买卖建议。</span>
          </div>
        </GlassCard>
      )}

      <Disclaimer />
    </div>
  );
}
