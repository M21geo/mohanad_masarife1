"""More > Settings: display currency, exchange rate, automatic backups."""
import flet as ft

from .. import backup, money, paths, reminder, reset
from . import kit, theme as T
from .forms import choices, label
from .rows import page_frame


def build_settings(ui):
    repo = ui.repo
    rate = kit.field("سعر الصرف (دينار لكل 1 دولار)", f"{repo.get_rate():g}", thousands=True)

    def save_rate(e):
        v = money.parse_input(rate.value)
        if v <= 0:
            ui.toast("اكتب سعراً صحيحاً")
            return
        ui.guard(repo.set_rate, v)
        ui.toast("تم حفظ السعر")
        ui.refresh()

    def set_cur(c):
        repo.set_setting("display_currency", c)
        ui.currency = c
        ui.refresh()

    def set_auto(v):
        repo.set_setting("auto_backup", "1" if v else "0")
        ui.refresh()

    def set_hide(v):
        repo.set_setting("hide_balances", "1" if v else "0")
        ui.refresh()

    cfg = reminder.settings(repo)

    def set_reminder(v):
        repo.set_setting("reminder_enabled", "1" if v else "0")
        if v:
            repo.set_setting("reminder_last", "")
        ui.refresh()

    def set_time(t):
        repo.set_setting("reminder_time", t)
        repo.set_setting("reminder_last", "")
        ui.refresh()

    def safety_backup():
        try:
            backup.create_backup(repo, paths.backup_dir(), keep=5, prefix="pre-reset")
        except Exception:
            pass

    def do_clear():
        safety_backup()
        reset.clear_transactions(repo)
        ui.toast("تم مسح كل المعاملات والديون")
        ui.refresh()

    def do_factory():
        safety_backup()
        reset.factory_reset(repo)
        ui.currency = repo.get_setting("display_currency", "IQD") or "IQD"
        ui.toast("تمت إعادة الضبط. ابدأ من جديد")
        ui.refresh()

    auto = (repo.get_setting("auto_backup", "1") == "1")
    return page_frame(ui, "الإعدادات", [
        kit.box(kit.col([label("العملة الافتراضية للعرض"), choices([("IQD", "دينار"), ("USD", "دولار")], ui.currency, set_cur)], spacing=10)),
        kit.box(kit.col([label("سعر الصرف"), rate, kit.big_button("حفظ السعر", save_rate),
                         kit.txt("السعر يُستخدم في التحويلات بين المحافظ وفي الإحصائيات (حسب سعر اليوم).", 12, color=T.MUTED)], spacing=10)),
        kit.box(kit.between(kit.col([kit.txt("إخفاء الأرصدة", 15, True),
                                     kit.txt("يعرض •••• بدل الأرصدة بالرئيسية والمحافظ", 12, color=T.MUTED)], spacing=2),
                            ft.Switch(value=ui.hide_balances, on_change=lambda e: set_hide(e.control.value)))),
        kit.box(kit.col([
            kit.between(kit.col([kit.txt("تذكير يومي", 15, True),
                                 kit.txt("يطلع تنبيه داخل التطبيق إذا ما سجلت شي اليوم أو عندك قسط قريب", 12, color=T.MUTED)], spacing=2),
                        ft.Switch(value=cfg["enabled"], on_change=lambda e: set_reminder(e.control.value))),
            ft.Container(kit.row([kit.icon("schedule", 20, T.PRIMARY), kit.txt("وقت التذكير: " + cfg["time"], 14, True)], spacing=8),
                         ink=True, border_radius=10, padding=8, on_click=lambda e: kit.pick_time(ui, cfg["time"], set_time)),
            kit.txt("التنبيه يظهر لما يكون التطبيق مفتوح. التنبيهات خارج التطبيق تحتاج مكوّن أندرويد إضافي (نرجع له بخطوة الـAPK).", 11, color=T.FAINT)],
            spacing=8)),
        kit.box(kit.between(kit.col([kit.txt("نسخة احتياطية تلقائية يومية", 15, True),
                                     kit.txt("تحفظ داخل التطبيق وتبقي آخر 7 نسخ", 12, color=T.MUTED)], spacing=2),
                            ft.Switch(value=auto, on_change=lambda e: set_auto(e.control.value)))),
        kit.box(kit.col([
            kit.txt("مسح البيانات (البدء من جديد)", 15, True, T.EXPENSE),
            kit.txt("تُحفظ نسخة أمان تلقائياً قبل أي مسح (تلقاها بشاشة النسخ الاحتياطي). الهستوري ما ينمسح.", 12, color=T.MUTED),
            kit.big_button("مسح كل المعاملات والديون", lambda e: kit.confirm_typed(
                ui.page, "مسح المعاملات", "تنحذف كل المعاملات والديون. تبقى المحافظ (بأرصدتها الابتدائية) والفئات والأشخاص والميزانيات.", "مسح", do_clear),
                outline=True),
            kit.big_button("إعادة ضبط كاملة", lambda e: kit.confirm_typed(
                ui.page, "إعادة ضبط كاملة", "يتم مسح كل شي: المحافظ والمعاملات والفئات والأشخاص والديون والملاحظات والميزانيات، ويرجع التطبيق مثل أول مرة.", "مسح", do_factory),
                bg=T.EXPENSE)], spacing=10)),
    ])
