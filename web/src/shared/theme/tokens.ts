// Every colour, size and duration the console uses. CSS reads the same values as custom properties (global.css).
export const color = {
  paper: "#F4F6F9",
  surface: "#FFFFFF",
  ink: "#172033",
  inkMuted: "#4A5468",
  rule: "#D5DAE3",
  accent: "#1F4FA8",
  tick: "#1D6B47", // verified: the auditor's green tick
  pencil: "#B42318", // an error: the auditor's red pencil
  watch: "#8A5300",
} as const;

export const space = { xs: 4, sm: 8, md: 16, lg: 24, xl: 40 } as const;
export const radius = { sm: 4, md: 8 } as const;

export const motionTiming = {
  enter: { duration: 0.22, ease: [0.2, 0.8, 0.2, 1] as const },
  stagger: 0.04,
} as const;

// Forest plot geometry (Results screen)
export const plot = { width: 420, rowHeight: 34, dot: 5, axisTicks: [0, 0.25, 0.5, 0.75, 1] } as const;

export const layout = { nav: 220, pageMax: 1180, reviewImage: 640 } as const;
