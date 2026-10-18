import os
import tempfile
import threading
import unittest
import zipfile

from app import importer
from app.db import connect
from app.history import Histories
from app.repo import AppError, Repo
from app.seed import ensure_defaults


def make_xlsx(path, sheets, shared=True, workbook_order=None, with_r=True, strict_ns=False):
    """Hand-built minimal .xlsx. sheets: {filename: rows}; cell values str or number."""
    ns = "http://purl.oclc.org/ooxml/spreadsheetml/main" if strict_ns else "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    strings = []

    def cell(ref, v):
        r = f' r="{ref}"' if with_r else ""
        if isinstance(v, (int, float)):
            return f"<c{r}><v>{v}</v></c>"
        if shared:
            strings.append(v)
            return f'<c{r} t="s"><v>{len(strings) - 1}</v></c>'
        return f'<c{r} t="inlineStr"><is><t>{v}</t></is></c>'

    with zipfile.ZipFile(path, "w") as z:
        sheet_entries, rels = [], []
        for i, (fname, rows) in enumerate(sheets.items(), start=1):
            body = ""
            for ri, row in enumerate(rows, start=1):
                body += f'<row r="{ri}">' + "".join(cell(f"{chr(65 + ci)}{ri}", v) for ci, v in enumerate(row)) + "</row>"
            z.writestr(f"xl/worksheets/{fname}", f'<worksheet xmlns="{ns}"><sheetData>{body}</sheetData></worksheet>')
            sheet_entries.append(f'<sheet name="S{i}" sheetId="{i}" r:id="rId{i}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>')
            rels.append(f'<Relationship Id="rId{i}" Target="worksheets/{fname}"/>')
        order = workbook_order or list(range(len(sheet_entries)))
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}"><sheets>{"".join(sheet_entries[i] for i in order)}</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", f"<Relationships>{''.join(rels)}</Relationships>")
        if shared:
            z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{ns}">' + "".join(f"<si><r><t>{s}</t></r></si>" for s in strings) + "</sst>")


ROWS = [["التاريخ", "المبلغ", "العملة", "الفئة"], [45200, 5000, "IQD", "طعام"], [45201, "12.5", "USD", "طعام"]]


class XlsxReaderTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def read(self, name, **kw):
        p = os.path.join(self.d, name)
        make_xlsx(p, **kw)
        return importer.read_table(p)

    def test_shared_inline_and_missing_refs(self):
        for kw in ({"shared": True}, {"shared": False}, {"shared": True, "with_r": False}, {"shared": True, "strict_ns": True}):
            h, rows = self.read("a.xlsx", sheets={"sheet1.xml": ROWS}, **kw)
            self.assertEqual(h, ["التاريخ", "المبلغ", "العملة", "الفئة"], kw)
            self.assertEqual(len(rows), 2)
            self.assertEqual(importer.parse_date(rows[0]["التاريخ"]), "2023-10-01")

    def test_first_sheet_in_workbook_order_and_numbered_sheets(self):
        h, rows = self.read("b.xlsx", sheets={"sheet2.xml": ROWS, "sheet10.xml": [["x", "y"], ["1", "2"]]})
        self.assertEqual(h[0], "التاريخ")
        h, rows = self.read("c.xlsx", sheets={"sheet1.xml": [["x", "y"], ["1", "2"]], "sheet2.xml": ROWS}, workbook_order=[1, 0])
        self.assertEqual(h[0], "التاريخ")   # workbook lists sheet2 first

    def test_empty_first_sheet_falls_through(self):
        h, _ = self.read("d.xlsx", sheets={"sheet1.xml": [["only header"]], "sheet2.xml": ROWS})
        self.assertEqual(h[0], "التاريخ")

    def test_bad_files_give_arabic_errors_not_crashes(self):
        bad = os.path.join(self.d, "bad.xlsx")
        with open(bad, "wb") as f:
            f.write(b"not a zip")
        with self.assertRaises(AppError):
            importer.read_table(bad)
        old = os.path.join(self.d, "old.xls")
        open(old, "wb").write(b"x")
        with self.assertRaises(AppError) as cm:
            importer.read_table(old)
        self.assertIn("xlsx", str(cm.exception))

    def test_scientific_amounts(self):
        self.assertEqual(float(importer.parse_amount("1.5E3")), 1500.0)


class MixedCurrencyTests(unittest.TestCase):
    def test_one_file_both_currencies_into_history(self):
        h = Histories(tempfile.mkdtemp())
        meta = h.create(draft=True)
        arch = h.open(meta["id"])
        rows = [{"d": "2019-01-01", "a": "-5000", "c": "IQD"}, {"d": "2019-01-02", "a": "-$20", "c": ""},
                {"d": "2019-01-03", "a": "7,500 د.ع", "c": ""}, {"d": "2019-01-04", "a": "-3", "c": ""}]
        items = importer.preview(arch, rows, {"date": "d", "amount": "a", "currency": "c"}, None, "USD")
        self.assertEqual([i["currency"] for i in items], ["IQD", "USD", "IQD", "USD"])   # last uses the fallback
        self.assertFalse(any(i["error"] for i in items))
        self.assertEqual(importer.commit(arch, items, None)["added"], 4)
        self.assertEqual(sorted(w["name"] for w in arch.list_wallets()), ["المحفظة (IQD)", "المحفظة (USD)"])

    def test_main_import_routes_usd_rows_to_a_usd_wallet(self):
        r = Repo(connect(":memory:"))
        ensure_defaults(r)
        cash = next(w["id"] for w in r.list_wallets() if w["currency"] == "IQD")
        usd = next(w["id"] for w in r.list_wallets() if w["currency"] == "USD")
        items = importer.preview(r, [{"d": "2026-10-01", "a": "-5000", "c": ""}, {"d": "2026-10-01", "a": "-$9", "c": ""}],
                                 {"date": "d", "amount": "a", "currency": "c"}, cash, "IQD")
        self.assertEqual([i["wallet_id"] for i in items], [cash, usd])


class ThreadTests(unittest.TestCase):
    def test_connection_usable_from_other_threads(self):
        r = Repo(connect(":memory:"))
        ensure_defaults(r)
        out = {}

        def work():
            try:
                out["n"] = len(r.list_wallets())
            except Exception as e:  # pragma: no cover
                out["err"] = e
        t = threading.Thread(target=work)
        t.start()
        t.join()
        self.assertEqual(out.get("n"), 2, out)


if __name__ == "__main__":
    unittest.main()
