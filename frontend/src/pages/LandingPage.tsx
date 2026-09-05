import { FormEvent, useState } from "react";
import { ArrowRight, Github, LineChart, LockKeyhole, Sparkles } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import previewImage from "@/assets/ai-hot-preview-tight.png";
import { useAuth } from "@/components/auth/AuthProvider";
import { landingPrimaryAction } from "@/lib/landingState";

const FEATURES = ["AI 热点", "每日复盘", "个股研究", "可追溯对话"];

export function LandingPage() {
  const { identity, ready, signIn, signInGuest } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [adminOpen, setAdminOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState<"guest" | "owner" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const action = landingPrimaryAction(identity);

  const finishAuthentication = () => {
    if (location.pathname === "/") navigate("/ai/news");
  };
  const enterAsGuest = async () => {
    setBusy("guest"); setError(null);
    try { await signInGuest(); finishAuthentication(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "访客入口暂时不可用"); }
    finally { setBusy(null); }
  };
  const submitAdmin = async (event: FormEvent) => {
    event.preventDefault();
    if (!password) return;
    setBusy("owner"); setError(null);
    try { await signIn(password); setPassword(""); finishAuthentication(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "管理员登录失败"); }
    finally { setBusy(null); }
  };

  return (
    <div className="landing-shell min-h-screen overflow-hidden px-5 py-5 sm:px-8 lg:px-12">
      <header className="mx-auto flex max-w-[1440px] items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5" aria-label="FT-Research 首页">
          <span className="grid h-9 w-9 place-items-center rounded-xl border border-primary/30 bg-primary/10 text-primary shadow-glow"><LineChart className="h-5 w-5" /></span>
          <span className="text-base font-extrabold tracking-tight">FT-<span className="text-primary">Research</span></span>
        </Link>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <a href="https://vincentli-website.com/" target="_blank" rel="noreferrer" className="transition-colors hover:text-foreground">作者主页</a>
          <a href="https://github.com/lizhuoheng273-debug/FT-Research" target="_blank" rel="noreferrer" aria-label="GitHub" className="rounded-lg border border-border/70 p-2 transition-colors hover:border-primary/50 hover:text-primary"><Github className="h-4 w-4" /></a>
        </div>
      </header>

      <main className="mx-auto grid min-h-[calc(100vh-84px)] max-w-[1440px] items-center gap-14 py-12 lg:grid-cols-[minmax(0,0.7fr)_minmax(560px,1.3fr)] lg:gap-8 lg:py-8">
        <section className="relative z-10 max-w-2xl">
          <p className="mb-5 flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.24em] text-primary"><Sparkles className="h-3.5 w-3.5" />AI × MARKET RESEARCH</p>
          <h1 className="text-balance text-5xl font-black leading-[0.96] tracking-[-0.055em] sm:text-6xl lg:text-[4.75rem]">
            个人 AI<br /><span className="text-primary text-glow">投研工作台</span>
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground sm:text-xl">一个聚合 AI、金融资讯与数据的投研平台</p>
          <div className="mt-7 flex flex-wrap gap-2">
            {FEATURES.map((feature) => <span key={feature} className="rounded-full border border-border/70 bg-card/50 px-3 py-1.5 text-xs text-muted-foreground">{feature}</span>)}
          </div>

          <div className="mt-9 max-w-md">
            {!ready ? (
              <button disabled className="w-full rounded-xl bg-primary px-5 py-3.5 font-semibold text-primary-foreground opacity-60">正在检查登录状态…</button>
            ) : action.kind === "workspace" ? (
              <button onClick={() => navigate(action.to)} className="group flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-5 py-3.5 font-semibold text-primary-foreground shadow-glow transition-transform hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background">
                {action.label}<ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </button>
            ) : (
              <>
                <button onClick={() => void enterAsGuest()} disabled={busy !== null} aria-busy={busy === "guest"} className="group flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-5 py-3.5 font-semibold text-primary-foreground shadow-glow transition-transform hover:-translate-y-0.5 disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background">
                  {busy === "guest" ? "正在进入…" : action.label}<ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                </button>
                <button type="button" onClick={() => { setAdminOpen((value) => !value); setError(null); }} aria-expanded={adminOpen} className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-border/80 px-5 py-3 text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
                  <LockKeyhole className="h-4 w-4" />管理员登录
                </button>
                {adminOpen && <form onSubmit={submitAdmin} className="mt-3 flex gap-2 rounded-xl border border-border/70 bg-card/70 p-2">
                  <label className="sr-only" htmlFor="landing-password">管理员密码</label>
                  <input id="landing-password" autoFocus type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="输入管理员密码" className="min-w-0 flex-1 rounded-lg border-0 px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary" />
                  <button disabled={!password || busy !== null} className="rounded-lg bg-muted px-4 py-2 text-sm font-medium transition-colors hover:bg-primary hover:text-primary-foreground disabled:opacity-50">{busy === "owner" ? "登录中…" : "登录"}</button>
                </form>}
              </>
            )}
            {error && <p role="alert" className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
          </div>
          <p className="mt-5 font-mono text-[11px] tracking-[0.12em] text-muted-foreground/55">不荐股 · 不预测 · 无倾向</p>
        </section>

        <section className="relative min-w-0" aria-label="AI 热点资讯界面预览">
          <div className="absolute -inset-12 -z-10 rounded-full bg-primary/10 blur-3xl" />
          <div className="overflow-hidden rounded-2xl border border-border/70 bg-[#070b14] shadow-[0_32px_90px_rgba(0,0,0,0.55)]">
            <div className="flex h-10 items-center gap-2 border-b border-white/5 bg-white/[0.025] px-4">
              <span className="h-2.5 w-2.5 rounded-full bg-primary/80" /><span className="h-2.5 w-2.5 rounded-full bg-amber-400/50" /><span className="h-2.5 w-2.5 rounded-full bg-emerald-400/50" />
              <span className="ml-3 font-mono text-[10px] text-slate-500">research.vincentli-website.com · AI 热点资讯</span>
            </div>
            <div className="overflow-hidden bg-[#070b14]">
              <img src={previewImage} alt="FT-Research AI 热点资讯工作台" className="block h-auto w-full" />
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
