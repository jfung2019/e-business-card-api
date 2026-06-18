WALLET_CARD_PALETTES: list[dict[str, str]] = [
    {"background": "#D4F54A", "text": "#1A1A1A", "muted": "#4A5A00", "accent": "#B8D600"},
    {"background": "#FF6B5B", "text": "#FFFFFF", "muted": "#FFE8E5", "accent": "#FF8A7D"},
    {"background": "#7B4DFF", "text": "#FFFFFF", "muted": "#E8DEFF", "accent": "#9B7AFF"},
    {"background": "#F8F4EC", "text": "#1A1A1A", "muted": "#6B6B6B", "accent": "#C9A962"},
    {"background": "#2DD4BF", "text": "#0F3D36", "muted": "#CCFBF1", "accent": "#14B8A6"},
    {"background": "#F472B6", "text": "#FFFFFF", "muted": "#FCE7F3", "accent": "#EC4899"},
]


def palette_for_token(token: str) -> dict[str, str]:
    index = sum(ord(char) for char in token) % len(WALLET_CARD_PALETTES)
    return WALLET_CARD_PALETTES[index]
