import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/App";
import { resolveAdapters } from "@/adapters";
import { reportVitalsTo } from "@/lib/vitals";
import { CONFIG } from "@/lib/config";
import "@/styles/index.css";

const adapters = resolveAdapters();

// la medición de rendimiento sale por el mismo sink que el resto de eventos
if (CONFIG.vitalsEnabled) reportVitalsTo(adapters.analytics);

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(
    <React.StrictMode>
      <App adapters={adapters} />
    </React.StrictMode>,
  );
}
