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

function LegacyResearch() {
  const [params] = useSearchParams();
  const code = params.get("code");
  if (code && /^\d{6}$/.test(code)) return <Navigate to={`/finance/stocks/${code}`} replace />;
  return <StockData />;
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
      { path: "/finance/news", element: <Intel /> },
      { path: "/finance/news/:tab", element: <Intel /> },
      { path: "/finance/review", element: <DailyReview /> },
      { path: "/finance/watchlist", element: <Watchlist /> },
      { path: "/finance/stocks/:code", element: <StockDetail /> },
      { path: "/finance/indices/:code", element: <IndexDetail /> },
      { path: "/finance/research", element: <LegacyResearch /> },
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
      { path: "/debate", element: <Debate /> },
      { path: "/watchlist", element: <Watchlist /> },
      { path: "/my-reports", element: <MyReports /> },
      { path: "/notes", element: <Notes /> },
      { path: "/settings", element: <Settings /> },
    ],
  },
]);
