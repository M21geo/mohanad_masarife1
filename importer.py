"""Import past transactions from other apps' files (CSV / Excel .xlsx / JSON).

Flow used by the Import screen:
    headers, rows = read_table(path)                 # 1. choose a file
    mapping = guess_mapping(headers)                 # 2. user confirms/edits column mapping
    items = preview(repo, rows, mapping, options)    # 3. review: errors, duplicates, new items
    result = commit(repo, items, backup_dir=...)     # 4. save (auto-backup first, skips dups)
"""
import csv
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from . import money
from .backup import create_backup, export_data, import_data
from .repo import AppError, Repo

FIELDS = ["date", "amount", "kind", "category", "subcategory", "wallet", "currency", "person", "note"]

# header keywords (lower-case) -> field. First match wins, longer/specific first.
_HINTS = [
    ("subcategory", ["subcategory", "sub category", "sub-category", "فئة فرعية", "الفئة الفرعية", "فرعي"]),
    ("category", ["category", "categories", "فئة", "الفئة", "تصنيف", "التصنيف", "بند"]),
    ("date", ["date", "day", "time", "تاريخ", "التاريخ", "اليوم", "وقت"]),
    ("amount", ["amount", "value", "sum", "price", "total", "مبلغ", "المبلغ", "قيمة", "القيمة", "سعر"]),
    ("kind", ["type", "kind", "income/expense", "نوع", "النوع", "حركة"]),
    ("wallet", ["wallet", "account", "source", "محفظة", "المحفظة", "حساب", "الحساب"]),
    ("currency", ["currency", "curr", "عملة", "العملة"]),
    ("person", ["person", "payee", "contact", "name", "شخص", "الشخص", "اسم", "الاسم", "مع"]),
    ("note", ["note", "notes", "memo", "description", "details", "ملاحظة", "ملاحظات", "الملاحظات", "وصف", "تفاصيل"]),
]

_KIND_WORDS = {
    "expense": ["expense", "expenses", "out", "debit", "spend", "spent", "withdraw", "مصروف", "مصاريف", "صرف", "سحب", "خرج", "صادر"],
    "income": ["income", "in", "credit", "deposit", "salary", "earn", "دخل", "إيراد", "ايراد", "وارد", "قبض", "إيداع", "ايداع", "راتب"],
    "transfer": ["transfer", "تحويل", "نقل"],
}

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


# ----------------------------------------------------------------- reading
def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1256", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_xlsx(path: str) -> list:
    """Minimal .xlsx reader: the first sheet in workbook order that has data. Namespace-agnostic.
    Returns a list of row lists of strings (dates arrive as Excel serial numbers)."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
                if _local(si.tag) == "si":
                    shared.append("".join(t.text or "" for t in si.iter() if _local(t.tag) == "t"))
        # sheet files in workbook order (fallback: by file name)
        order = []
        try:
            rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
            for sh in ET.fromstring(z.read("xl/workbook.xml")).iter():
                if _local(sh.tag) == "sheet":
                    rid = next((v for k, v in sh.attrib.items() if _local(k) == "id"), None)
                    target = rels.get(rid)
                    if target:
                        order.append(target.lstrip("/") if target.startswith("/") else "xl/" + target)
        except (KeyError, ET.ParseError):
            pass
        order = [n for n in order if n in names] or sorted(
            (n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)), key=lambda n: int(re.findall(r"\d+", n)[-1]))
        if not order:
            raise AppError("ملف Excel ما بيه أوراق")
        for sheet in order:
            rows = _sheet_rows(ET.fromstring(z.read(sheet)), shared)
            if len(rows) >= 2:
                return rows
    return rows


def _sheet_rows(root, shared: list) -> list:
    rows = []
    for r in root.iter():
        if _local(r.tag) != "row":
            continue
        cells, nxt = {}, 0
        for c in r:
            if _local(c.tag) != "c":
                continue
            ref = c.get("r")
            idx = _col_index(ref) if ref else nxt
            nxt = idx + 1
            t = c.get("t")
            v = next((x for x in c if _local(x.tag) == "v"), None)
            if t == "s" and v is not None and v.text is not None:
                val = shared[int(v.text)] if int(v.text) < len(shared) else ""
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter() if _local(x.tag) == "t")
            else:
                val = v.text if v is not None and v.text is not None else ""
            cells[idx] = val
        if cells:
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return rows


def read_table(path: str):
    """Read a CSV/TSV/XLSX/JSON file -> (headers, rows) where each row is a dict header->str."""
    low = path.lower()
    if low.endswith(".xls"):
        raise AppError("صيغة xls القديمة غير مدعومة. افتح الملف بـ Excel واحفظه بصيغة xlsx أو csv ثم ارفعه")
    if low.endswith((".ods", ".numbers", ".pdf", ".zip")):
        raise AppError("صيغة الملف غير مدعومة. استخدم csv أو xlsx أو json")
    try:
        if low.endswith(".xlsx"):
            grid = _read_xlsx(path)
        elif low.endswith(".json"):
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = next((v for v in data.values() if isinstance(v, list)), [])
            if not data or not isinstance(data[0], dict):
                raise AppError("ملف JSON لازم يحتوي قائمة من السجلات")
            headers = list(dict.fromkeys(k for r in data for k in r))
            return headers, [{h: "" if r.get(h) is None else str(r.get(h)) for h in headers} for r in data]
        else:
            with open(path, "rb") as f:
                text = _decode(f.read())
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            grid = list(csv.reader(io.StringIO(text), dialect))
    except AppError:
        raise
    except Exception as e:  # any parsing problem is reported, never crashes the screen
        raise AppError(f"ما كدرت أقرأ الملف ({type(e).__name__}): {e}")
    grid = [r for r in grid if any(str(c).strip() for c in r)]
    if len(grid) < 2:
        raise AppError("الملف ما يحتوي بيانات")
    headers = [str(h).strip() or f"عمود {i + 1}" for i, h in enumerate(grid[0])]
    rows = [{h: (str(r[i]).strip() if i < len(r) else "") for i, h in enumerate(headers)} for r in grid[1:]]
    return headers, rows


# ----------------------------------------------------------------- mapping
def guess_mapping(headers: list) -> dict:
    """Suggest field -> header. Unmatched fields are simply absent."""
    mapping, used = {}, set()
    lowered = {h: h.strip().lower() for h in headers}
    for field, words in _HINTS:
        for h, lo in lowered.items():
            if h in used:
                continue
            if any(lo == w or w in lo for w in words):
                mapping[field] = h
                used.add(h)
                break
    return mapping


# ----------------------------------------------------------------- parsing
def parse_amount(text) -> Decimal:
    s = str(text).strip().translate(_DIGITS)
    if not s:
        raise ValueError("المبلغ فارغ")
    if re.fullmatch(r"[+-]?\d+(\.\d+)?[eE][+-]?\d+", s):  # Excel may store 1.5E3
        return Decimal(s)
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-") or s.endswith("-") or "−" in s
    s = re.sub(r"[^\d.,]", "", s.replace("٫", ".").replace("٬", ","))
    if "," in s and "." in s:  # 1,234.56 or 1.234,56
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:  # 1,234 (thousands) vs 12,5 (decimal)
        s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    try:
        v = Decimal(s)
    except InvalidOperation:
        raise ValueError("مبلغ غير مفهوم")
    return -v if neg else v


def parse_date(text, day_first: bool = True) -> str:
    s = str(text).strip().translate(_DIGITS)
    if not s:
        raise ValueError("التاريخ فارغ")
    if re.fullmatch(r"\d{5}(\.\d+)?", s) and 20000 < float(s) < 80000:  # Excel serial
        return (datetime(1899, 12, 30) + timedelta(days=int(float(s)))).date().isoformat()
    s = re.split(r"[ T]", s)[0]
    fmts = ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"]
    fmts += (["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y"] if day_first
             else ["%m/%d/%Y", "%m-%d-%Y", "%m.%d.%Y", "%m/%d/%y", "%m-%d-%y"])
    for f in fmts:
        try:
            return datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    raise ValueError("تاريخ غير مفهوم")


def parse_kind(text) -> Optional[str]:
    s = str(text).strip().lower()
    for kind, words in _KIND_WORDS.items():
        if s in words:
            return kind
    return None


def detect_currency(text) -> str:
    """Currency hinted by a symbol/word inside an amount cell ('$50', '25,000 د.ع'); '' when unknown."""
    s = str(text).lower()
    if "$" in s or "usd" in s or "دولار" in s:
        return "USD"
    if "iqd" in s or "د.ع" in s or "دينار" in s or "ع.د" in s:
        return "IQD"
    return ""


# ----------------------------------------------------------------- preview
def preview(repo: Repo, rows: list, mapping: dict, default_wallet_id: Optional[int] = None,
            default_currency: str = "IQD", day_first: bool = True, default_kind: str = "expense",
            sign_means_kind: bool = True) -> list:
    """Parse every row without saving. Each item has `error` (row will be skipped),
    `duplicate` (already in the app), and `new_wallet/new_category/new_person` flags."""
    if "date" not in mapping or "amount" not in mapping:
        raise AppError("لازم تحدد عمود التاريخ وعمود المبلغ")
    wallets = {w["name"].strip().casefold(): w for w in repo.list_wallets(include_archived=True)}
    default_wallet = repo.get_wallet(default_wallet_id) if default_wallet_id else None
    people = {p["name"].strip().casefold() for p in repo.list_people()}
    known_cats = {(c["kind"], c["name"].strip().casefold(), None) for k in ("expense", "income")
                  for c in repo.category_tree(k)}
    for k in ("expense", "income"):
        for top in repo.category_tree(k):
            for ch in top["children"]:
                known_cats.add((k, ch["name"].strip().casefold(), top["name"].strip().casefold()))

    def get(row, field):
        h = mapping.get(field)
        return row.get(h, "").strip() if h else ""

    items = []
    for n, row in enumerate(rows, start=2):  # row 1 = headers
        it = {"row": n, "error": None, "duplicate": False, "new_wallet": False,
              "new_category": False, "new_person": False}
        try:
            raw = parse_amount(get(row, "amount"))
            it["date"] = parse_date(get(row, "date"), day_first)
            kind = parse_kind(get(row, "kind")) if get(row, "kind") else None
            if kind is None:
                if get(row, "kind"):
                    raise ValueError(f"نوع غير مفهوم: {get(row, 'kind')}")
                kind = ("expense" if raw < 0 else "income") if sign_means_kind and "kind" not in mapping else default_kind
            if kind == "transfer":
                raise ValueError("التحويلات ما تنستورد. أضفها يدوياً")
            it["kind"], it["amount"] = kind, abs(raw)
            if it["amount"] == 0:
                raise ValueError("المبلغ صفر")
            it["note"] = get(row, "note")
            it["person"] = get(row, "person")
            it["new_person"] = bool(it["person"]) and it["person"].casefold() not in people
            cur = get(row, "currency").upper().replace("$", "USD").replace("دولار", "USD").replace("دينار", "IQD")
            if cur and cur not in money.CURRENCIES:
                raise ValueError(f"عملة غير مدعومة: {cur}")
            cur = cur or detect_currency(get(row, "amount"))
            wname = get(row, "wallet")
            if wname:
                w = wallets.get(wname.casefold())
                it["wallet_name"] = wname
                if w:
                    it["wallet_id"], it["currency"] = w["id"], w["currency"]
                    if cur and cur != w["currency"]:
                        raise ValueError("عملة المعاملة تخالف عملة المحفظة")
                else:
                    it["wallet_id"], it["currency"], it["new_wallet"] = None, cur or default_currency, True
            else:
                # no wallet column: use the default wallet when its currency fits, otherwise a wallet of the
                # row's own currency (an existing one, or a new "المحفظة (USD)") - so a file may mix IQD and USD
                want = cur or (default_wallet["currency"] if default_wallet else default_currency)
                if default_wallet and default_wallet["currency"] == want:
                    it["wallet_name"], it["wallet_id"], it["currency"] = default_wallet["name"], default_wallet["id"], want
                else:
                    w = next((x for x in wallets.values() if x["currency"] == want and not x["archived"]), None)
                    if w:
                        it["wallet_name"], it["wallet_id"], it["currency"] = w["name"], w["id"], want
                    else:
                        it["wallet_name"], it["wallet_id"], it["currency"], it["new_wallet"] = f"المحفظة ({want})", None, want, True
            it["category"], it["subcategory"] = get(row, "category"), get(row, "subcategory")
            if it["subcategory"] and not it["category"]:
                it["category"], it["subcategory"] = it["subcategory"], ""
            name = (it["subcategory"] or it["category"]).strip().casefold()
            parent = it["category"].strip().casefold() if it["subcategory"] else None
            it["new_category"] = bool(name) and (kind, name, parent) not in known_cats
        except (ValueError, KeyError, TypeError, AttributeError, InvalidOperation) as e:
            it["error"] = str(e) or type(e).__name__
        items.append(it)
    _mark_duplicates(repo, items)
    return items


def _key(it, wallet_id):
    return (it["date"], it["kind"], money.to_minor(it["amount"], it["currency"]), wallet_id, it["note"])


def _mark_duplicates(repo: Repo, items: list) -> None:
    """A row is a duplicate when the app already holds that many identical rows
    (so two real identical coffees in one file are both kept on first import,
    but re-importing the same file adds nothing)."""
    seen = Counter()
    for it in items:
        if it["error"] or it.get("wallet_id") is None:
            continue
        k = _key(it, it["wallet_id"])
        have = repo.conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE date=? AND kind=? AND amount=? AND wallet_id=? AND note=?",
            k).fetchone()[0]
        it["duplicate"] = seen[k] < have
        seen[k] += 1


# ------------------------------------------------------------------ commit
def summarize(items: list) -> dict:
    ok = [i for i in items if not i["error"]]
    return {
        "total": len(items),
        "errors": sum(1 for i in items if i["error"]),
        "duplicates": sum(1 for i in ok if i["duplicate"]),
        "to_add": sum(1 for i in ok if not i["duplicate"]),
        "new_wallets": len({i["wallet_name"] for i in ok if i["new_wallet"]}),
        "new_categories": len({(i["kind"], i["category"], i["subcategory"]) for i in ok if i["new_category"]}),
        "new_people": len({i["person"] for i in ok if i["new_person"]}),
    }


def commit(repo: Repo, items: list, backup_dir: Optional[str] = None) -> dict:
    """Save the importable rows. A safety backup is written first, and if anything
    fails midway the app data is rolled back to exactly how it was."""
    todo = [i for i in items if not i["error"] and not i["duplicate"]]
    if not todo:
        return {"added": 0, "skipped": len(items)}
    snapshot = export_data(repo)
    if backup_dir:
        create_backup(repo, backup_dir, keep=5, prefix="pre-import")
    wallets = {w["name"].strip().casefold(): w["id"] for w in repo.list_wallets(include_archived=True)}
    people = {p["name"].strip().casefold(): p["id"] for p in repo.list_people()}
    cat_cache = {}

    def category_id(kind, cat, sub):
        if not (cat or sub):
            return None
        key = (kind, cat.casefold(), sub.casefold())
        if key in cat_cache:
            return cat_cache[key]
        tree = repo.category_tree(kind)
        top = next((t for t in tree if t["name"].strip().casefold() == cat.strip().casefold()), None)
        top_id = top["id"] if top else repo.add_category(kind, cat)
        cid = top_id
        if sub:
            child = next((c for c in (top["children"] if top else []) if c["name"].strip().casefold() == sub.strip().casefold()), None)
            cid = child["id"] if child else repo.add_category(kind, sub, parent_id=top_id)
        cat_cache[key] = cid
        return cid

    added = 0
    try:
        for it in todo:
            wid = it["wallet_id"]
            if wid is None:
                k = it["wallet_name"].strip().casefold()
                if k not in wallets:
                    wallets[k] = repo.add_wallet(it["wallet_name"], it["currency"])
                wid = wallets[k]
            pid = None
            if it["person"]:
                k = it["person"].strip().casefold()
                if k not in people:
                    people[k] = repo.add_person(it["person"])
                pid = people[k]
            cid = category_id(it["kind"], it["category"], it["subcategory"])
            adder = repo.add_expense if it["kind"] == "expense" else repo.add_income
            adder(wid, it["amount"], cid, pid, it["note"], it["date"])
            added += 1
    except Exception:
        import_data(repo, snapshot, "replace")
        raise
    return {"added": added, "skipped": len(items) - added}
