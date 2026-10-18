"""Add / edit transaction sheet: expense, income or transfer between wallets."""
import flet as ft

from .. import money
from ..budgets import Budgets
from . import kit, theme as T, vm

KINDS = [("expense", "مصروف"), ("income", "دخل"), ("transfer", "تحويل")]
DATES = [("today", "اليوم"), ("yesterday", "أمس"), ("two_days", "قبل يومين")]


def open_add_sheet(ui, tx=None, kind=None):
    repo, editing = ui.repo, tx is not None
    wallets = repo.list_wallets()
    if not wallets:
        ui.toast("أضف محفظة أولاً")
        return
    s = {
        "kind": tx["kind"] if editing else (kind or "expense"),
        "wallet": tx["wallet_id"] if editing else wallets[0]["id"],
        "to_wallet": (tx["to_wallet_id"] if editing else None),
        "cat": tx["category_id"] if editing else None,
        "person": tx["person_id"] if editing else None,
        "date": tx["date"] if editing else ui.today,
        "date_choice": None if editing else "today",
    }
    if s["kind"] == "transfer" and s["to_wallet"] is None:
        others = [w for w in wallets if w["id"] != s["wallet"]]
        s["to_wallet"] = others[0]["id"] if others else None

    def wallet_by_id(i):
        return next((w for w in repo.list_wallets(True) if w["id"] == i), wallets[0])

    amount = kit.field("المبلغ", "" if not editing else str(money.from_minor(tx["amount"], tx["currency"])),
                       on_change=lambda e: render() if s["kind"] == "transfer" else None, thousands=True)
    note = kit.field("ملاحظة (اختياري)", tx["note"] if editing else "", multiline=True)
    rate_f = kit.field("سعر الصرف (دينار لكل 1$)", f"{repo.get_rate():g}", on_change=lambda e: render(), thousands=True)
    body = ft.Column(spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
    sheet_ref = {}

    parse = money.parse_input

    def cat_chips():
        kind = s["kind"]
        tree = repo.category_tree(kind)
        top = next((c for c in tree if c["id"] == s["cat"] or any(ch["id"] == s["cat"] for ch in c["children"])), None)
        chips = [kit.chip("بدون فئة", s["cat"] is None, lambda e: pick("cat", None))]
        chips += [kit.chip(c["name"], top is not None and c["id"] == top["id"],
                           lambda e, i=c["id"]: pick("cat", i), color=c["color"] or T.PRIMARY) for c in tree]
        chips.append(kit.chip("+ فئة", False, lambda e: new_category(None)))
        out = [kit.txt("الفئة", 13, True, T.MUTED), ft.Row(chips, wrap=True, spacing=8, run_spacing=8)]
        if top and not top["children"]:
            out += [ft.Row([kit.chip("+ فئة فرعية", False, lambda e, i=top["id"]: new_category(i), color=T.MUTED)])]
        if top and top["children"]:
            subs = [kit.chip(f"كل {top['name']}", s["cat"] == top["id"], lambda e, i=top["id"]: pick("cat", i), color=T.MUTED)]
            subs += [kit.chip(ch["name"], s["cat"] == ch["id"], lambda e, i=ch["id"]: pick("cat", i), color=T.MUTED)
                     for ch in top["children"]]
            subs.append(kit.chip("+ فرعية", False, lambda e, i=top["id"]: new_category(i)))
            out += [kit.txt("الفئة الفرعية", 13, True, T.MUTED), ft.Row(subs, wrap=True, spacing=8, run_spacing=8)]
        return out

    def pick(key, value):
        s[key] = value
        if key == "kind":
            s["cat"] = None
            if value == "transfer" and (s["to_wallet"] in (None, s["wallet"])):
                others = [w for w in wallets if w["id"] != s["wallet"]]
                s["to_wallet"] = others[0]["id"] if others else None
        if key == "wallet" and s["to_wallet"] == value:
            others = [w for w in wallets if w["id"] != value]
            s["to_wallet"] = others[0]["id"] if others else None
        render()

    def preview():
        """Transfer between different currencies: show what the other wallet receives."""
        if s["kind"] != "transfer" or s["to_wallet"] is None:
            return []
        a, b = wallet_by_id(s["wallet"]), wallet_by_id(s["to_wallet"])
        if a["currency"] == b["currency"]:
            return []
        try:
            got = money.convert_minor(money.to_minor(parse(amount.value), a["currency"]), a["currency"], b["currency"],
                                      parse(rate_f.value) or repo.get_rate())
        except Exception:
            got = 0
        return [rate_f, kit.box(kit.txt(f"المستلم: {money.fmt(got, b['currency'])}", 15, True, T.PRIMARY),
                                bg=T.PRIMARY_SOFT, border=None)]

    def save(e):
        def run():
            amt = parse(amount.value)
            if amt <= 0:
                ui.toast("اكتب المبلغ")
                return False
            if editing:
                if tx["kind"] == "transfer":
                    repo.update_transaction(tx["id"], note=note.value, date=s["date"])
                else:
                    repo.update_transaction(tx["id"], amount=amt, category_id=s["cat"], person_id=s["person"],
                                            note=note.value, date=s["date"])
            elif s["kind"] == "transfer":
                if s["to_wallet"] is None:
                    ui.toast("تحتاج محفظتين للتحويل")
                    return False
                same = wallet_by_id(s["wallet"])["currency"] == wallet_by_id(s["to_wallet"])["currency"]
                repo.add_transfer(s["wallet"], s["to_wallet"], amt, rate=None if same else (parse(rate_f.value) or None),
                                  note=note.value, date=s["date"])
            else:
                add = repo.add_expense if s["kind"] == "expense" else repo.add_income
                add(s["wallet"], amt, category_id=s["cat"], person_id=s["person"], note=note.value, date=s["date"])
            return True

        if ui.guard(run):
            ui.page.close(sheet_ref["sheet"])
            msg = "تم الحفظ"
            if s["kind"] == "expense" and not (editing and tx["kind"] == "transfer"):
                try:
                    alerts = Budgets(repo).alerts(s["date"][:7], ui.today, s["cat"])
                    if alerts:
                        msg = "⚠️ " + " · ".join(alerts)
                except Exception:
                    pass
            ui.toast(msg)
            ui.refresh()

    def new_category(parent_id):
        name = kit.field("فرعية جديدة" if parent_id else "اسم الفئة")

        def ok(ev):
            def run():
                s["cat"] = repo.add_category(s["kind"], name.value, parent_id=parent_id)
                return True
            if ui.guard(run):
                ui.page.close(dlg)
                render()

        dlg = ft.AlertDialog(title=ft.Text("فئة فرعية جديدة" if parent_id else "فئة جديدة"), content=name,
                             actions=[ft.TextButton("إلغاء", on_click=lambda ev: ui.page.close(dlg)),
                                      ft.TextButton("إضافة", on_click=ok)])
        ui.page.open(dlg)

    def add_person(e):
        name = kit.field("اسم الشخص")

        def ok(ev):
            def run():
                s["person"] = repo.add_person(name.value)
                return True
            if ui.guard(run):
                ui.page.close(dlg)
                render()

        dlg = ft.AlertDialog(title=ft.Text("شخص جديد"), content=name,
                             actions=[ft.TextButton("إلغاء", on_click=lambda ev: ui.page.close(dlg)),
                                      ft.TextButton("إضافة", on_click=ok)])
        ui.page.open(dlg)

    def render():
        kind = s["kind"]
        parts = []
        if not editing:
            parts.append(kit.segmented(KINDS, kind, lambda k: pick("kind", k)))
        else:
            parts.append(kit.txt("تعديل معاملة", 20, True))
        parts.append(amount)
        wchips = [kit.chip(f"{w['name']} ({w['currency']})", s["wallet"] == w["id"],
                           (lambda e, i=w["id"]: pick("wallet", i)) if not editing else None) for w in wallets]
        parts += [kit.txt("من محفظة" if kind == "transfer" else "المحفظة", 13, True, T.MUTED),
                  ft.Row(wchips, wrap=True, spacing=8, run_spacing=8)]
        if kind == "transfer":
            tchips = [kit.chip(f"{w['name']} ({w['currency']})", s["to_wallet"] == w["id"],
                               (lambda e, i=w["id"]: pick("to_wallet", i)) if not editing else None)
                      for w in wallets if w["id"] != s["wallet"]]
            parts += [kit.txt("إلى محفظة", 13, True, T.MUTED), ft.Row(tchips, wrap=True, spacing=8, run_spacing=8)]
            parts += preview() if not editing else []
        else:
            parts += cat_chips()
            people = repo.list_people()
            pchips = [kit.chip("بدون", s["person"] is None, lambda e: pick("person", None))]
            pchips += [kit.chip(p["name"], s["person"] == p["id"], lambda e, i=p["id"]: pick("person", i)) for p in people]
            pchips.append(kit.chip("+ شخص", False, add_person))
            parts += [kit.txt("الشخص", 13, True, T.MUTED), ft.Row(pchips, wrap=True, spacing=8, run_spacing=8)]
        dchips = [kit.chip(label, s["date_choice"] == key,
                           lambda e, k=key: (s.update(date=vm.relative_date(k, ui.today), date_choice=k), render()))
                  for key, label in DATES]
        def custom(iso):
            s.update(date=iso, date_choice="custom")
            render()

        dchips.append(kit.chip("📅 " + (s["date"] if s["date_choice"] in (None, "custom") else "تاريخ آخر"),
                               s["date_choice"] in (None, "custom"),
                               lambda e: kit.pick_date(ui, s["date"], custom)))
        parts += [kit.txt("التاريخ", 13, True, T.MUTED), ft.Row(dchips, wrap=True, spacing=8, run_spacing=8),
                  note, kit.big_button("حفظ التعديل" if editing else "حفظ", save)]
        body.controls = parts
        ui.page.update()

    sheet_ref["sheet"] = ui.open_sheet(body)
    render()
