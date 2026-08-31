import { useEffect, useRef, useState } from "react";
import { api, type Quote } from "@/lib/api";

export function isAStockTradingTime(now = new Date()): boolean {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(now);
  const read = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value || "";
  if (["Sat", "Sun"].includes(read("weekday"))) return false;
  const minutes = Number(read("hour")) * 60 + Number(read("minute"));
  return (minutes >= 570 && minutes <= 690) || (minutes >= 780 && minutes <= 900);
}

export function useLiveStockQuote(code: string) {
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState(false);
  const requestIdRef = useRef(0);

  useEffect(() => {
    setQuote(null);
    setError(false);
    const refresh = () => {
      const requestId = ++requestIdRef.current;
      api.quote(code)
        .then((rows) => {
          if (requestId !== requestIdRef.current) return;
          setQuote(rows[code] || null);
          setError(!rows[code]);
        })
        .catch(() => {
          if (requestId !== requestIdRef.current) return;
          setQuote(null);
          setError(true);
        });
    };
    refresh();
    const poll = window.setInterval(() => {
      if (document.visibilityState === "visible" && isAStockTradingTime()) refresh();
    }, 15_000);
    const onVisibility = () => {
      if (document.visibilityState === "visible" && isAStockTradingTime()) refresh();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(poll);
      document.removeEventListener("visibilitychange", onVisibility);
      requestIdRef.current += 1;
    };
  }, [code]);

  return { quote, error };
}
