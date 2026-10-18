"""Colors and sizes shared by every screen (same palette as the design mockups)."""

BG = "#F3F5F4"
CARD = "#FFFFFF"
LINE = "#E3E8E6"
SOFT = "#EEF2F0"
INK = "#12201D"
MUTED = "#5E6E69"
FAINT = "#8A9A95"

PRIMARY = "#0B6B58"
PRIMARY_SOFT = "#DDF3EC"
HERO = "#0F2A26"
HERO_CARD = "#1B403A"
HERO_TEXT = "#B9D4CD"
MINT = "#7FE0C3"

INCOME = "#0B7A4B"
EXPENSE = "#B42318"
TRANSFER = "#2B4C9B"

# chart palette (validated for colour-blind separation)
CHART_INCOME = "#2a78d6"
CHART_EXPENSE = "#eb6834"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]

TONE = {  # tone -> (text colour, background)
    "income": (INCOME, "#DDF3EC"),
    "expense": (EXPENSE, "#FDE7E3"),
    "neutral": (MUTED, SOFT),
    "good": ("#0B4A3D", "#DDF3EC"),
    "bad": ("#8A1C12", "#FDE7E3"),
    "warn": ("#7A4A00", "#FDF0D5"),
}

DEFAULT_WIDTH = 390  # used until the real window width is known
