import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { LegalPage } from "./LegalPage";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {["/aviso-legal", "/privacidad", "/cookies"].includes(window.location.pathname) ? (
      <LegalPage path={window.location.pathname} />
    ) : (
      <App />
    )}
  </StrictMode>,
);
