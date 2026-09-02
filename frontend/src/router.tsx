import { createBrowserRouter, Navigate, useSearchParams } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { DailyReview } from "@/pages/DailyReview";
import { Intel } from "@/pages/Intel";
import { Signals } from "@/pages/Signals";
import { Sectors } from "@/pages/Sectors";
import { SectorDetail } from "@/pages/SectorDetail";
import { Debate } from "@/pages/Debate";
import { Portfolio } from "@/pages/Portfolio";
import { StockData } from "@/pages/StockData";
import { Watchlist } from "@/pages/Watchlist";
import { MyReports } from "@/pages/MyReports";
import { Notes } from "@/pages/Notes";
import { Settings } from "@/pages/Settings";
import { AINews } from "@/pages/AINews";
import { AIDaily } from "@/pages/AIDaily";
import { AINewsDetail } from "@/pages/AINewsDetail";
import { StockDetail } from "@/pages/StockDetail";
import { IndexDetail } from "@/pages/IndexDetail";
import { FinanceAiWorkspace } from "@/pages/FinanceAiWorkspace";
import { FinancialNews } from "@/pages/FinancialNews";
import { FinancialNewsDetail } from "@/pages/FinancialNewsDetail";

function LegacyResearch() {
  const [params] = useSearchParams();
  const code = params.get("code");
  if (code && /^\d{6}$/.test(code)) return <Navigate to={`/finance/stocks/${code}`} replace />;
  return <StockData />;
}

function RetiredResearch() {
  const [params] = useSearchParams();
  return params.get("code") ? <LegacyResearch /> : <Navigate to="/finance/debate" replace />;
}

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Navigate to="/ai/news" replace /> },
      { path: "/ai/news", element: <AINews /> },
      { path: "/ai/news/story/:storyId", element: <AINewsDetail /> },
      { path: "/ai/news/:tab", element: <AINews /> },
      { path: "/ai/daily", element: <AIDaily /> },
      { path: "/finance/news", element: <FinancialNews /> },
      { path: "/finance/news/story/:eventId", element: <FinancialNewsDetail /> },
      { path: "/finance/news/:tab", element: <FinancialNews /> },
      { path: "/finance/review", element: <DailyReview /> },
      { path: "/finance/ai", element: <FinanceAiWorkspace /> },
      { path: "/finance/watchlist", element: <Watchlist /> },
      { path: "/finance/stocks/:code", element: <StockDetail /> },
      { path: "/finance/stocks/:code/ai", element: <FinanceAiWorkspace /> },
      { path: "/finance/indices/:code", element: <IndexDetail /> },
      { path: "/finance/research", element: <RetiredResearch /> },
      { path: "/finance/debate", element: <Debate /> },
      // Legacy deep links remain available for existing bookmarks.
      { path: "/daily-review", element: <DailyReview /> },
      { path: "/intel", element: <Intel /> },
      { path: "/intel/:tab", element: <Intel /> },
      { path: "/signals", element: <Signals /> },
      { path: "/signals/:tab", element: <Signals /> },
      { path: "/sectors", element: <Sectors /> },
      { path: "/sectors/:key", element: <SectorDetail /> },
      { path: "/portfolio", element: <Portfolio /> },
      { path: "/stock-data", element: <LegacyResearch /> },
      { path: "/debate", element: <Navigate to="/finance/debate" replace /> },
      { path: "/watchlist", element: <Watchlist /> },
      { path: "/my-reports", element: <MyReports /> },
      { path: "/notes", element: <Notes /> },
      { path: "/settings", element: <Settings /> },
    ],
  },
]);
