import type { ReactNode } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { LandingPage } from "@/pages/LandingPage";

export function AuthGate({ children }: { children: ReactNode }) {
  const { identity } = useAuth();
  if (identity) return <>{children}</>;
  return <LandingPage />;
}
