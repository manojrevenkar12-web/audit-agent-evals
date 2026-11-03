import { useEffect, useState } from "react";
import { JudgeScreen } from "../features/judge/JudgeScreen";
import { ReleasesScreen } from "../features/releases/ReleasesScreen";
import { ResultsScreen } from "../features/results/ResultsScreen";
import { ReviewScreen } from "../features/review/ReviewScreen";

const SCREENS = {
  results: { title: "Results", view: ResultsScreen },
  releases: { title: "Releases", view: ReleasesScreen },
  judge: { title: "Judge", view: JudgeScreen },
  review: { title: "Review queue", view: ReviewScreen },
} as const;
type Screen = keyof typeof SCREENS;

function fromHash(): Screen {
  const h = window.location.hash.replace("#/", "");
  return h in SCREENS ? (h as Screen) : "results";
}

export function App() {
  const [screen, setScreen] = useState<Screen>(fromHash);
  useEffect(() => {
    const on = () => setScreen(fromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  useEffect(() => {
    document.title = `${SCREENS[screen].title} · Audit agent evals`;
  }, [screen]);
  const View = SCREENS[screen].view;
  return (
    <div className="shell">
      <header className="nav">
        <div className="nav__brand">
          Audit agent evals
          <small>Quality of the review agents</small>
        </div>
        <nav aria-label="Main">
          <ul>
            {(Object.keys(SCREENS) as Screen[]).map((s) => (
              <li key={s}>
                <button
                  type="button"
                  aria-current={s === screen ? "page" : undefined}
                  onClick={() => {
                    window.location.hash = `#/${s}`;
                  }}
                >
                  {SCREENS[s].title}
                </button>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main className="main" id="main">
        <View />
      </main>
    </div>
  );
}
