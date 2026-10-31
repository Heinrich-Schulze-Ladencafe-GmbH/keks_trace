import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

WOCHENTAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


class Linie(Document):
	def validate(self):
		if (self.laufzeit_stunden or 0) <= 0:
			frappe.throw(_("Bitte eine Laufzeit pro Tag größer 0 angeben."))
		falsch = [t for t in self.tage() if t not in WOCHENTAGE]
		if falsch or not self.tage():
			frappe.throw(_("Arbeitstage bitte als Mo,Di,Mi,Do,Fr,Sa,So angeben."))

	def tage(self) -> list[str]:
		return [t.strip().capitalize() for t in (self.arbeitstage or "").split(",") if t.strip()]

	def ist_arbeitstag(self, datum) -> bool:
		return WOCHENTAGE[getdate(datum).weekday()] in self.tage()
