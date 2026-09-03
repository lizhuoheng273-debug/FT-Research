import { useEffect, useState } from "react";
import { Check, KeyRound, ShieldCheck, X } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { apiUrl, authHeaders, loadAccessKey, saveAccessKey } from "@/lib/api";

interface AiStatus { configured: boolean; model: string; base_url: string; key_present: boolean }

export function Settings() {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [accessKey, setAccessKey] = useState(loadAccessKey);

  useEffect(() => {
    fetch(apiUrl("/ai/status"), { headers: authHeaders() })
      .then((r) => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then(setStatus)
      .catch(() => setError("暂时无法读取后端状态，请确认 FastAPI 已启动"));
  }, []);

  const saveAccess = () => saveAccessKey(accessKey.trim());

  return (
    <div>
      <PageHeader title="AI 投研配置" subtitle="GLM 由后端统一管理，浏览器不会保存或发送模型 API Key" />
      <GlassCard className="mb-4">
        <div className="flex items-center gap-2">
          {status?.configured ? <Check className="h-5 w-5 text-success" /> : <X className="h-5 w-5 text-destructive" />}
          <h3 className="font-semibold">GLM 5.3 Flash</h3>
          <span className={status?.configured ? "text-success" : "text-muted-foreground"}>{status?.configured ? "已配置" : "未配置"}</span>
        </div>
        <div className="mt-3 grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
          <p>模型：<b className="text-foreground">{status?.model || "glm-5.3-flash"}</b></p>
          <p>接口：<b className="text-foreground">{status?.base_url || "https://open.bigmodel.cn/api/paas/v4"}</b></p>
        </div>
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        <p className="mt-4 rounded-lg border border-success/25 bg-success/5 p-3 text-xs text-muted-foreground">
          <ShieldCheck className="mr-1 inline h-4 w-4 text-success" />
          请将 <code>GLM_API_KEY</code> 写入 <code>backend/.env</code>。状态接口只返回是否已配置，不会返回密钥。
        </p>
      </GlassCard>

      <GlassCard>
        <h3 className="mb-1 flex items-center gap-1.5 text-sm font-semibold"><KeyRound className="h-4 w-4 text-primary" /> 后端访问密钥（可选）</h3>
        <p className="mb-3 text-xs text-muted-foreground">仅当部署时设置了 VR_API_KEY 才需要填写，用于防止公网接口被滥用。</p>
        <div className="flex items-center gap-2">
          <input type="password" value={accessKey} onChange={(e) => setAccessKey(e.target.value)} placeholder="VR_API_KEY"
            className="flex-1 rounded-lg border border-border bg-input px-3 py-2 text-sm text-input-foreground outline-none placeholder:text-input-placeholder focus:border-primary/50" />
          <button onClick={saveAccess} className="rounded-lg bg-primary/15 px-4 py-2 text-sm font-medium text-primary hover:bg-primary/25">保存</button>
        </div>
      </GlassCard>
    </div>
  );
}
