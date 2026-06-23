# Design System — PS Price 2050

## Aesthetic

Futuristic deal intelligence terminal. Not a dashboard — a cinematic command center. Inspired by high-end AI-generated web experiences: cursor-reactive atmosphere, 3D tilt cards, holographic borders, floating dock navigation.

## Typography

- **Display:** Syne (800/700 for heroes, -0.03em tracking)
- **Data:** JetBrains Mono (prices, labels, system copy)

## Themes (4 visual modes)

| ID | Name | Character |
|----|------|-----------|
| nebula | Nebula | Deep space cobalt + cyan beam |
| eclipse | Eclipse | Solar magenta + teal accent |
| void | Void | Absolute black + gold signal |
| fusion | Fusion | Plasma violet + amber reactor |

Switch via glowing orb picker in header. Stored in localStorage.

## Key effects

- Cursor-following spotlight (Scene)
- Animated ambient orbs + perspective grid
- Film grain + scanline overlay
- Holo panels (blur + bright border)
- Rotating conic-gradient borders on featured cards
- 3D perspective tilt on deal cards (motion)
- Neon buttons with sweep shine
- Floating dock nav with layoutId indicator
- Cmd+K command palette search
- Live deal ticker marquee

## Layout

- Top bar: logo mark + search + theme orbs + status pill
- Bottom floating dock (desktop) / tab bar (mobile)
- Homepage: cinematic hero → stats bento → ticker → filter matrix → featured bento → deal grid
