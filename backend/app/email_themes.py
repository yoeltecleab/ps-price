"""Theme color palettes for HTML notification emails."""

from __future__ import annotations

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
}

DEFAULT_THEME_ID = "abyss"


def palette_for(theme_id: str | None) -> dict[str, str]:
    if theme_id and theme_id in THEME_PALETTES:
        return THEME_PALETTES[theme_id]
    return THEME_PALETTES[DEFAULT_THEME_ID]
