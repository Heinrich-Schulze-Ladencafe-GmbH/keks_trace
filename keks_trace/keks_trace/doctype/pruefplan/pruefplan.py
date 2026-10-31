import frappe
from frappe import _
from frappe.model.document import Document


class Pruefplan(Document):
	def validate(self):
		if self.art == "Messwert":
			if self.grenze("min_wert") is None and self.grenze("max_wert") is None:
				frappe.throw(_("Bitte einen Grenzwert (mindestens oder höchstens) angeben."))
			for f in ("min_wert", "max_wert"):
				if (self.get(f) or "").strip() and self.grenze(f) is None:
					frappe.throw(_("{0} ist keine Zahl.").format(self.get(f)))
		if self.art == "Prüfkörper" and not self.koerper():
			frappe.throw(_("Bitte die Prüfkörper angeben (einer pro Zeile)."))
		if self.ausloeser == "Regelmäßig an der Station" and (self.intervall_minuten or 0) <= 0:
			frappe.throw(_("Bitte ein Intervall in Minuten angeben."))

	def grenze(self, feld):
		wert = (self.get(feld) or "").strip().replace(",", ".")
		try:
			return float(wert) if wert else None
		except ValueError:
			return None

	def koerper(self) -> list[str]:
		return [k.strip() for k in (self.pruefkoerper or "").splitlines() if k.strip()]
