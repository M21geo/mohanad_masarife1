"""First-run defaults: two wallets, starter categories, default exchange rate.

Everything seeded here can be edited/reordered/deleted by the user from Settings.
Colors come from the validated chart palette used in the design mockups.
"""
from .repo import Repo

# icon names are Flet/Material icon names (used by the UI in the next step)
EXPENSE = [
    ("طعام", "restaurant", "#2a78d6", ["مطاعم", "بقالة", "قهوة", "توصيل"]),
    ("مواصلات", "directions_car", "#eb6834", ["وقود", "تكسي", "صيانة"]),
    ("فواتير", "bolt", "#1baf7a", ["كهرباء", "إنترنت", "ماء"]),
    ("تسوق", "shopping_bag", "#eda100", ["ملابس", "أجهزة"]),
    ("صحة", "favorite", "#e87ba4", ["دواء", "طبيب"]),
]
INCOME = [
    ("راتب", "payments", "#1baf7a", []),
    ("عمل حر", "work", "#2a78d6", []),
    ("هدية", "card_giftcard", "#eda100", []),
]


def ensure_defaults(repo: Repo) -> bool:
    """Seed an empty database. Returns True if anything was created."""
    if repo.list_wallets(include_archived=True) or repo.category_tree("expense") or repo.category_tree("income"):
        return False
    repo.add_wallet("نقد", "IQD")
    repo.add_wallet("دولار نقد", "USD")
    repo.set_setting("base_currency", "IQD")
    repo.set_setting("rate", 1480)
    for kind, items in (("expense", EXPENSE), ("income", INCOME)):
        for name, icon, color, subs in items:
            parent = repo.add_category(kind, name, icon=icon, color=color)
            for sub in subs:
                repo.add_category(kind, sub, parent_id=parent, icon=icon, color=color)
    return True
