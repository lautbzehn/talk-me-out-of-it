import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { domAnimation, LazyMotion } from "motion/react";
import "./index.css";
import App from "./App";

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root element.");

// The site only fades, slides and springs things in, so it loads Motion's animation features alone
// (no drag, layout or gesture code). Components use `m.div` instead of `motion.div`; `strict` makes
// a stray `motion.div` throw at once, so the bigger build can't creep back in unnoticed.
createRoot(root).render(
  <StrictMode>
    <LazyMotion features={domAnimation} strict>
      <App />
    </LazyMotion>
  </StrictMode>,
);
