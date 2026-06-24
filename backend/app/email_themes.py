"""Theme color palettes for HTML notification emails.

Price-drop emails are HTML (not plain text) so they can look nice in inbox
apps. Users can pick a theme on their watch; this module maps theme **ids**
(e.g. ``"abyss"``) to hex color codes used in the email template built by
``notifier.py``.

Each palette has the same keys:
  - bg, surface — page and card backgrounds
  - ink, muted  — primary and secondary text
  - primary, accent — links and highlights
  - border — dividers
"""

from __future__ import annotations

# All available themes. Keys are stored on watches as ``theme_id``.
THEME_PALETTES: dict[str, dict[str, str]] = {
    "abyss": {
        "bg": "#020308",
        "surface": "#0a0c14",
        "ink": "#eceef4",
        "muted": "#7a8299",
        "primary": "#4a6fd4",
        "accent": "#5eead4",
        "border": "#1a2030",
    },
    "void": {
        "bg": "#050505",
        "surface": "#0f1014",
        "ink": "#f2f2f5",
        "muted": "#8a8a95",
        "primary": "#5a7ae8",
        "accent": "#f5d547",
        "border": "#222228",
    },
    "nebula": {
        "bg": "#08061a",
        "surface": "#120f28",
        "ink": "#eee8ff",
        "muted": "#9a8fbf",
        "primary": "#7c5cff",
        "accent": "#ff6bcb",
        "border": "#2a2248",
    },
    "midnight": {
        "bg": "#040810",
        "surface": "#0c1420",
        "ink": "#e8f0ff",
        "muted": "#7a90b0",
        "primary": "#3b82f6",
        "accent": "#22d3ee",
        "border": "#1a2840",
    },
    "dawn": {
        "bg": "#f8f6f2",
        "surface": "#ffffff",
        "ink": "#1a1a22",
        "muted": "#6b6b78",
        "primary": "#4f46e5",
        "accent": "#0891b2",
        "border": "#e4e0d8",
    },
    "frost": {
        "bg": "#f0f7ff",
        "surface": "#ffffff",
        "ink": "#0f172a",
        "muted": "#64748b",
        "primary": "#2563eb",
        "accent": "#0ea5e9",
        "border": "#dbeafe",
    },
    "eclipse": {"bg": "#0a0510", "surface": "#140a1c", "ink": "#f5e8ff", "muted": "#a78bb8", "primary": "#c026d3", "accent": "#f472b6", "border": "#2d1a3d"},
    "crimson": {"bg": "#0c0404", "surface": "#180808", "ink": "#ffe8e8", "muted": "#b88a8a", "primary": "#dc2626", "accent": "#f97316", "border": "#3d1a1a"},
    "forest": {"bg": "#030a06", "surface": "#081410", "ink": "#e8f5ee", "muted": "#7a9a88", "primary": "#16a34a", "accent": "#4ade80", "border": "#1a3024"},
    "fusion": {"bg": "#0a0514", "surface": "#140a24", "ink": "#f0e8ff", "muted": "#a88fd4", "primary": "#a855f7", "accent": "#e879f9", "border": "#2a1a48"},
    "ink": {"bg": "#0a0a0c", "surface": "#141418", "ink": "#ececee", "muted": "#888890", "primary": "#52525b", "accent": "#a1a1aa", "border": "#27272a"},
    "dusk": {"bg": "#0c0a14", "surface": "#16121f", "ink": "#ebe8f4", "muted": "#8a849c", "primary": "#7c3aed", "accent": "#a78bfa", "border": "#2a2438"},
    "graphite": {"bg": "#101012", "surface": "#1a1a1e", "ink": "#e8e8ec", "muted": "#7a7a84", "primary": "#52525b", "accent": "#94a3b8", "border": "#2a2a30"},
    "paper": {"bg": "#faf9f6", "surface": "#ffffff", "ink": "#1c1917", "muted": "#78716c", "primary": "#44403c", "accent": "#0d9488", "border": "#e7e5e4"},
    "sand": {"bg": "#faf6f0", "surface": "#fffdf9", "ink": "#292524", "muted": "#78716c", "primary": "#b45309", "accent": "#d97706", "border": "#e7e0d6"},
    "sky": {"bg": "#f0f9ff", "surface": "#ffffff", "ink": "#0c4a6e", "muted": "#64748b", "primary": "#0284c7", "accent": "#38bdf8", "border": "#dbeafe"},
    "mint": {"bg": "#f0fdf4", "surface": "#ffffff", "ink": "#14532d", "muted": "#64748b", "primary": "#059669", "accent": "#34d399", "border": "#d1fae5"},
    "pearl": {"bg": "#fdf8ff", "surface": "#ffffff", "ink": "#3b0764", "muted": "#7e7490", "primary": "#9333ea", "accent": "#e879f9", "border": "#f3e8ff"},
}

DEFAULT_THEME_ID = "abyss"


def palette_for(theme_id: str | None) -> dict[str, str]:
    """Return the color dict for ``theme_id``, or the default theme if unknown."""
    if theme_id and theme_id in THEME_PALETTES:
        return THEME_PALETTES[theme_id]
    return THEME_PALETTES[DEFAULT_THEME_ID]
