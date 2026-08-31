import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import {
  Activity, Radar, Search, Moon, Sun, ChevronsLeft, ChevronsRight, LineChart, Github, UserRound,
  Star, FileText, Newspaper,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDarkMode } from "@/hooks/useDarkMode";
import { storageGet, storageSet } from "@/lib/storage";

// 具名导入：只把 version 打进产物，不会把整个 package.json 塞进 bundle
import { version as PKG_VERSION } from "../../../package.json";

// 版本号只从 package.json 读，不再各处写死（发 v0.3.0 时三处忘改停在 v0.2.2，#20）
const APP_VERSION = `v${PKG_VERSION}`;
const REPO_URL = "https://github.com/lizhuoheng273-debug/FT-Research";
// 作者联系方式
const X_URL = "https://x.com/linsizhen";
const MAIL_URL = "mailto:simonlin0423@gmail.com";

const NAV = [
  { to: "/ai/news", icon: Radar, label: "AI 热点资讯", section: "AI 板块" },
  { to: "/ai/daily", icon: FileText, label: "AI 日报" },
  { to: "/finance/review", icon: Activity, label: "每日复盘", section: "金融板块" },
  { to: "/finance/news", icon: Newspaper, label: "金融市场资讯" },
  { to: "/finance/watchlist", icon: Star, label: "自选股" },
  { to: "/finance/research", icon: Search, label: "AI 投研" },
];

export function Layout() {
  const { pathname } = useLocation();
  const stockAiWorkspace = /^\/finance\/stocks\/\d{6}\/ai$/.test(pathname);
  const { dark, toggle } = useDarkMode();
  const [collapsed, setCollapsed] = useState(() => storageGet("vr-sidebar") === "collapsed");
  useEffect(() => {
    storageSet("vr-sidebar", collapsed ? "collapsed" : "expanded");
  }, [collapsed]);

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className={cn(
        "glass z-10 m-2 flex shrink-0 flex-col rounded-2xl transition-all duration-200",
        collapsed ? "w-14" : "w-60",
      )}>
        {/* Brand */}
        <div className={cn("border-b border-border/50", collapsed ? "flex justify-center p-3" : "p-4")}>
          <Link to="/ai/news" className={cn("flex items-center", collapsed ? "justify-center" : "gap-2")}>
            <LineChart className="h-6 w-6 shrink-0 text-primary text-glow" />
            {!collapsed && (
              <span className="text-lg font-extrabold tracking-tight">
                FT-<span className="text-primary">Research</span>
              </span>
            )}
          </Link>
          {!collapsed && <p className="mt-1 text-[11px] text-muted-foreground">个人 AI 投研系统 · A股/美股/港股</p>}
        </div>

        {/* Nav */}
        <nav className={cn("flex-1 space-y-1 overflow-auto", collapsed ? "p-1.5" : "p-2.5")}>
          {NAV.map(({ to, icon: Icon, label, section }, index) => {
            const active = pathname === to || pathname.startsWith(`${to}/`);
            return (
              <div key={to}>
                {section && !collapsed && <p className={cn("px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground/50", index > 0 && "mt-4")}>{section}</p>}
                <Link
                  to={to}
                  title={collapsed ? label : undefined}
                  className={cn(
                    "flex items-center rounded-lg text-sm transition-colors",
                    collapsed ? "justify-center p-2.5" : "gap-2.5 px-3 py-2.5",
                    active
                      ? "bg-primary/15 font-medium text-primary shadow-glow"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {!collapsed && label}
                </Link>
              </div>
            );
          })}
        </nav>

        {/* Footer */}
        <div className={cn("border-t border-border/50", collapsed ? "flex flex-col items-center gap-2 p-2" : "space-y-2 p-3")}>
          {collapsed ? (
            <>
              <button onClick={toggle} className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title={dark ? "亮色" : "暗色"}>
                {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
              <a href={X_URL} target="_blank" rel="noreferrer" className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title="联系作者 · X @linsizhen">
                <UserRound className="h-4 w-4" />
              </a>
              <button onClick={() => setCollapsed(false)} className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title="展开">
                <ChevronsRight className="h-4 w-4" />
              </button>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <button onClick={toggle} className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground">
                  {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
                  {dark ? "亮色" : "暗色"}
                </button>
                <div className="flex items-center gap-2">
                  <a href={X_URL} target="_blank" rel="noreferrer" className="text-muted-foreground transition-colors hover:text-foreground" title="联系作者 · X @linsizhen">
                    <UserRound className="h-3.5 w-3.5" />
                  </a>
                  <a href={REPO_URL} target="_blank" rel="noreferrer" className="text-muted-foreground transition-colors hover:text-foreground" title="GitHub">
                    <Github className="h-3.5 w-3.5" />
                  </a>
                  <button onClick={() => setCollapsed(true)} className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground" title="收起">
                    <ChevronsLeft className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-1.5 text-[11px] text-primary/80">
                <span className="text-muted-foreground/60">联系作者</span>
                <a href={X_URL} target="_blank" rel="noreferrer" className="transition-colors hover:text-primary">X</a>
                <span className="text-muted-foreground/40">·</span>
                <a href={MAIL_URL} className="transition-colors hover:text-primary">Email</a>
              </div>
              <p className="text-[11px] leading-relaxed text-muted-foreground/60">
                {APP_VERSION} · 不荐股 · 不预测 · 无倾向
              </p>
            </>
          )}
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <div className={cn("mx-auto", stockAiWorkspace ? "max-w-none px-3 py-3" : "max-w-6xl px-6 py-6")}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
