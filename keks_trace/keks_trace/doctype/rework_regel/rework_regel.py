import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from keks_trace.install import REWORK_ZIELE


class ReworkRegel(Document):
	def validate(self):
		if frappe.get_cached_value("Item", self.rework_artikel, "kt_chargen_stufe") != "Rework":
			frappe.throw(
				_("{0} ist kein Rework-Artikel (Chargenstufe muss 'Rework' sein).").format(
					self.rework_artikel
				)
			)
		if frappe.get_cached_value("Item", self.ziel_artikel, "kt_chargen_stufe") not in REWORK_ZIELE:
			frappe.throw(
				_("{0} ist kein Teig (Chargenstufe muss {1} sein).").format(
					self.ziel_artikel, " oder ".join(REWORK_ZIELE)
				)
			)
		if not 0 < flt(self.max_anteil_prozent) <= 100:
			frappe.throw(_("Der maximale Rework-Anteil muss zwischen 0 und 100 % liegen."))

		doppelt = frappe.db.exists(
			"Rework Regel",
			{
				"rework_artikel": self.rework_artikel,
				"ziel_artikel": self.ziel_artikel,
				"name": ["!=", self.name],
			},
		)
		if doppelt:
			frappe.throw(
				_("Für {0} in {1} gibt es bereits die Regel {2}.").format(
					self.rework_artikel, self.ziel_artikel, doppelt
				)
			)
