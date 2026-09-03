import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { AuthProvider } from "./components/auth/AuthProvider";
import { router } from "./router";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <ErrorBoundary>
        <RouterProvider router={router} />
        <Toaster position="bottom-right" theme="dark" richColors closeButton duration={3500} />
      </ErrorBoundary>
    </AuthProvider>
  </StrictMode>
);
