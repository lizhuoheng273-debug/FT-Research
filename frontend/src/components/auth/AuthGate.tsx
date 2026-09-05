import { FormEvent, useState, type ReactNode } from "react";
import { useAuth } from "@/components/auth/AuthProvider";

export function AuthGate({ children }: { children: ReactNode }) {
  const { identity, ready, signIn, signInGuest } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (!ready) return <div className="flex min-h-screen items-center justify-center text-muted-foreground">正在检查登录状态…</div>;
  if (identity) return <>{children}</>;
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(null);
    try { await signIn(password); setPassword(""); } catch (reason) { setError(reason instanceof Error ? reason.message : "登录失败"); }
  };
  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="glass w-full max-w-md rounded-2xl p-7">
        <h1 className="text-2xl font-extrabold">FT-<span className="text-primary">Research</span></h1>
        <p className="mt-2 text-sm text-muted-foreground">管理员登录可恢复历史；访客体验仅在当前页面保留。</p>
        <form onSubmit={submit} className="mt-6 space-y-3">
          <label className="block text-sm"><span className="mb-1 block">管理员密码</span><input aria-label="管理员密码" type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded-lg border border-border bg-input px-3 py-2 text-input-foreground placeholder:text-input-placeholder" /></label>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <button className="w-full rounded-lg bg-primary px-3 py-2 font-medium text-primary-foreground">管理员登录</button>
        </form>
        <button onClick={() => void signInGuest().catch((reason) => setError(reason instanceof Error ? reason.message : "访客入口失败"))} className="mt-3 w-full rounded-lg border border-border px-3 py-2">访客体验</button>
        <p className="mt-4 text-xs text-muted-foreground">访客刷新或退出后无法找回本次临时记录。</p>
      </div>
    </div>
  );
}
