import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Settings, Sparkles, Trash2, X } from "lucide-react";
import { AiConversation } from "@/components/ai/AiConversation";
import { useAiChatSession } from "@/hooks/useAiChatSession";
import { hasLlm, type AnalysisScope } from "@/lib/llm";
import { buildAiWorkspacePath, type AiWorkspaceSource } from "@/lib/financeAi";

interface Props {
  context: string;
  suggestions?: string[];
  label?: string;
  scopeKey?: string;
  analysisScope?: AnalysisScope;
  workspaceSource?: AiWorkspaceSource;
  workspaceCode?: string;
  workspacePanel?: string;
  workspaceEventId?: string;
  workspaceDate?: string;
}

// 紧凑入口继续服务日报、资讯与个股分类；会话与流式逻辑由共享 hook 管理，
// 个股顶部的大工作台使用同一套底层，不复制请求和持久化状态机。
export function AskAiButton({ context, suggestions = [], label = "问 AI", scopeKey, analysisScope = "general", workspaceSource, workspaceCode, workspacePanel, workspaceEventId, workspaceDate }: Props) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [configured, setConfigured] = useState(false);
  const session = useAiChatSession({
    conversationKey: pathname + (scopeKey ? `#${scopeKey}` : "") + `:framework:v2:${analysisScope}`,
    context,
    analysisScope,
  });

  useEffect(() => {
    if (open) setConfigured(hasLlm());
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  const close = () => {
    setOpen(false);
  };

  const openWorkspace = () => navigate(buildAiWorkspacePath(workspaceSource!, { code: workspaceCode, panel: workspacePanel, eventId: workspaceEventId, date: workspaceDate }), { state: { from: pathname + window.location.search } });

  if (workspaceSource) {
    return <button type="button" onClick={openWorkspace} className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-3 py-1.5 text-sm font-medium text-primary shadow-glow transition-colors hover:bg-primary/25"><Sparkles className="h-4 w-4" />{label}</button>;
  }

  return <>
    <button onClick={() => setOpen(true)} className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-3 py-1.5 text-sm font-medium text-primary shadow-glow transition-colors hover:bg-primary/25">
      <Sparkles className="h-4 w-4" />{label}
    </button>

    {open && <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={close} />
      <aside role="dialog" aria-modal="true" aria-label="问 AI" className="glass relative m-3 flex w-full max-w-md flex-col rounded-2xl">
        <div className="flex items-center justify-between border-b border-border/60 p-4">
          <span className="flex items-center gap-2 font-semibold text-glow"><Sparkles className="h-4 w-4 text-primary" />问 AI · 本页上下文</span>
          <div className="flex items-center gap-2">
            {session.messages.length > 0 && <button onClick={session.clearChat} title="清空本页对话" aria-label="清空本页对话" className="text-muted-foreground hover:text-foreground"><Trash2 className="h-4 w-4" /></button>}
            <button onClick={close} aria-label="关闭" className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
          </div>
        </div>

        {!configured ? <div className="flex-1 space-y-4 overflow-auto p-4 text-sm">
          <div className="rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs text-muted-foreground">分析结论由你自己配置的 AI 给出，本产品只负责整理上下文，<b className="text-foreground">不校准、不背书、不对结果负责</b>。</div>
          <div><p className="mb-1.5 text-xs font-medium text-muted-foreground">将随提问发给 AI 的本页上下文：</p><pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">{context}</pre></div>
          <Link to="/settings" className="flex items-center justify-center gap-2 rounded-lg bg-primary/15 px-3 py-2 text-sm font-medium text-primary hover:bg-primary/25"><Settings className="h-4 w-4" />先接入你的 AI（订阅 / API）</Link>
        </div> : <AiConversation session={session} suggestions={suggestions} mode="compact" />}
      </aside>
    </div>}
  </>;
}
