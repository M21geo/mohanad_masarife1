"""More > Import: CSV / XLSX / JSON from other apps -> column mapping -> preview -> import."""
import os

import flet as ft

from .. import importer, paths
from ..history import Histories
from ..repo import AppError
from . import kit, theme as T
from .forms import choices, label
from .rows import page_frame

FIELD_LABELS = {"date": "التاريخ *", "amount": "المبلغ *", "kind": "النوع (دخل/مصروف)", "category": "الفئة",
                "subcategory": "الفئة الفرعية", "wallet": "المحفظة", "currency": "العملة", "person": "الشخص", "note": "الملاحظة"}
SIGN = [("sign", "حسب الإشارة (سالب=مصروف)"), ("expense", "الكل مصروف"), ("income", "الكل دخل")]


def _state(ui):
    if getattr(ui, "imp", None) is None:
        ui.imp = {"path": None, "headers": [], "rows": [], "mapping": {}, "wallet": None, "day_first": True,
                  "sign": "sign", "items": None, "dest": "main", "hcur": "IQD", "draft": None, "error": ""}
    return ui.imp


def build_import(ui):
    repo, st = ui.repo, _state(ui)

    def drop_draft():
        if st.get("draft"):
            try:
                st["draft"]["repo"].conn.close()
                Histories(paths.history_dir()).delete(st["draft"]["meta"]["id"])
            except Exception:
                pass
            st["draft"] = None

    def reset(e=None):
        drop_draft()
        dest = st["dest"]
        ui.imp = None
        _state(ui)["dest"] = dest
        ui.refresh()

    def picked(path):
        st["error"] = ""
        try:
            headers, rows = importer.read_table(path)
            st.update(path=path, headers=headers, rows=rows, mapping=importer.guess_mapping(headers), items=None)
            wallets = repo.list_wallets()
            st["wallet"] = st["wallet"] or (wallets[0]["id"] if wallets else None)
        except AppError as e:
            st["error"] = f"{os.path.basename(path)}: {e}"
        except Exception as e:
            st["error"] = f"{os.path.basename(path)}: {type(e).__name__}: {e}"
        ui.refresh()

    if not st["path"]:
        return page_frame(ui, "استيراد", [
            kit.box(kit.col([kit.txt("استورد معاملاتك القديمة من تطبيقات أخرى", 15, True),
                             kit.txt("الملفات المدعومة: CSV وExcel (xlsx) وJSON. الصف الأول لازم يكون أسماء الأعمدة. "
                                     "تُحفظ نسخة أمان قبل الاستيراد، وإذا صار خطأ ترجع بياناتك كما كانت.", 13, color=T.MUTED)], spacing=8)),
            *([kit.box(kit.txt(st["error"], 13, color=T.EXPENSE), bg="#FDE7E3", border=None)] if st["error"] else []),
            kit.big_button("اختيار ملف", lambda e: kit.pick_file(ui, picked, ["csv", "tsv", "xlsx", "json", "txt"], "اختر ملف المعاملات"))])

    def set_map(field, value):
        if value:
            st["mapping"][field] = value
        else:
            st["mapping"].pop(field, None)
        st["items"] = None

    def dd(field):
        opts = [("", "— بدون —")] + [(h, h) for h in st["headers"]]
        return kit.dropdown(FIELD_LABELS[field], opts, st["mapping"].get(field, ""), lambda e, f=field: set_map(f, e.control.value))

    def opt(key, value):
        st[key] = value
        st["items"] = None
        if key in ("dest", "hcur"):
            drop_draft()
        ui.refresh()

    def target():
        """(repo, default_wallet_id, fallback_currency). History = a draft archive that starts EMPTY: wallets are created
        from the file (per currency), so one file may mix IQD and USD."""
        if st["dest"] != "history":
            wallet = repo.get_wallet(st["wallet"]) if st["wallet"] else None
            return repo, st["wallet"], wallet["currency"] if wallet else "IQD"
        if not st.get("draft"):
            hs = Histories(paths.history_dir())
            meta = hs.create(rate=repo.get_rate(), draft=True)
            st["draft"] = {"meta": meta, "repo": hs.open(meta["id"])}
        return st["draft"]["repo"], None, st["hcur"]

    def do_preview(e):
        sign = st["sign"]

        def run():
            trepo, wid, cur = target()
            return importer.preview(trepo, st["rows"], st["mapping"], wid, cur, st["day_first"],
                                    "income" if sign == "income" else "expense", sign == "sign")
        st["items"] = ui.guard(run)
        ui.refresh()

    def do_commit(e):
        if st["dest"] == "history":
            d = st["draft"]
            res = ui.guard(importer.commit, d["repo"], st["items"], None)
            if res is not None:
                Histories(paths.history_dir()).finalize(d["meta"]["id"])
                d["repo"].conn.close()
                name = d["meta"]["name"]
                st["draft"] = None
                ui.imp = None
                ui.toast(f"تم حفظ {res['added']} معاملة في «{name}» (بدون تأثير على التطبيق)")
                ui.more_page = "history"
                ui.refresh()
            return
        res = ui.guard(importer.commit, repo, st["items"], paths.backup_dir())
        if res is not None:
            ui.toast(f"تم استيراد {res['added']} معاملة")
            ui.imp = None
            ui.refresh()

    wallets = [(w["id"], f"{w['name']} ({w['currency']})") for w in repo.list_wallets()]
    parts = [
        kit.box(kit.col([kit.txt(os.path.basename(st["path"]), 14, True), kit.txt(f"{len(st['rows'])} صف", 12, color=T.MUTED),
                         kit.big_button("اختيار ملف آخر", reset, outline=True)], spacing=6)),
        *([kit.box(kit.txt(st["error"], 13, color=T.EXPENSE), bg="#FDE7E3", border=None)] if st["error"] else []),
        kit.txt("ربط الأعمدة", 15, True), *[dd(f) for f in importer.FIELDS],
        label("وين تنحفظ هذه المعاملات؟"),
        choices([("main", "التطبيق الرئيسي (تؤثر على الأرصدة)"), ("history", "هستوري معزول (أرشيف فقط)")], st["dest"], lambda v: opt("dest", v)),
        *([kit.txt("الهستوري ما يغيّر الأرصدة ولا فئاتك ولا أشخاصك، ويكوّن محافظه وفئاته وأشخاصه من الملف. الملف ممكن يحتوي دينار ودولار معاً "
                   "(من عمود العملة أو رمز $ بالمبلغ).", 12, color=T.MUTED),
           label("إذا ما تحددت العملة بالصف، اعتبرها"), choices([("IQD", "دينار"), ("USD", "دولار")], st["hcur"], lambda v: opt("hcur", v))]
          if st["dest"] == "history" else
          [label("المحفظة الافتراضية (للصفوف بدون عمود محفظة)"), choices(wallets, st["wallet"], lambda v: opt("wallet", v))]),
        label("ترتيب التاريخ"), choices([(True, "يوم/شهر/سنة"), (False, "شهر/يوم/سنة")], st["day_first"], lambda v: opt("day_first", v)),
        label("نوع المعاملة إذا ما في عمود نوع"), choices(SIGN, st["sign"], lambda v: opt("sign", v)),
        kit.big_button("معاينة", do_preview),
    ]
    items = st["items"]
    if items is not None:
        sm = importer.summarize(items)
        parts.append(kit.box(kit.col([
            kit.txt(f"سيُضاف {sm['to_add']} من {sm['total']}", 16, True, T.PRIMARY),
            kit.txt(f"مكرر (موجود مسبقاً): {sm['duplicates']} · أخطاء: {sm['errors']}", 13, color=T.MUTED),
            kit.txt(f"جديد: {sm['new_wallets']} محفظة · {sm['new_categories']} فئة · {sm['new_people']} شخص", 13, color=T.MUTED)], spacing=4),
            bg=T.PRIMARY_SOFT, border=None))
        bad = [i for i in items if i["error"]][:5]
        parts += [kit.txt(f"صف {i['row']}: {i['error']}", 12, color=T.EXPENSE) for i in bad]
        parts += [kit.txt(f"{i['date']} · {i['kind']} · {i['amount']} · {i.get('category') or ''}", 12, color=T.MUTED)
                  for i in [x for x in items if not x["error"]][:6]]
        parts.append(kit.big_button(f"استيراد {sm['to_add']} معاملة" if st["dest"] == "main" else f"حفظ {sm['to_add']} معاملة كهستوري",
                                    do_commit, enabled=sm["to_add"] > 0))
    return page_frame(ui, "استيراد", parts)
