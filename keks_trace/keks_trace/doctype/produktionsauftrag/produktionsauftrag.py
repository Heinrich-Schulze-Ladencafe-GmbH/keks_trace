import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

FEST_AB_START = ("linie", "artikel", "menge", "einheit", "kundenauftrag")


class Produktionsauftrag(Document):
	def validate(self):
		from keks_trace import palette

		if frappe.get_cached_value("Item", self.artikel, "kt_chargen_stufe") != "Fertigware":
			frappe.throw(_("Ein Produktionsauftrag ist für Fertigware. {0} ist keine.").format(self.artikel))
		if flt(self.menge) <= 0:
			frappe.throw(_("Bitte eine Menge größer 0 angeben."))
		self.menge_kg = flt(flt(self.menge) * palette.faktor(self.artikel, self.einheit), 3)
		from keks_trace.planung import leistung

		kg_h, engpass, anlage = leistung(self.artikel, self.verpackungsanlage)
		if not kg_h:
			frappe.throw(
				_("Für {0} ist keine Leistung je Linienabschnitt eingetragen (am Artikel).").format(
					self.artikel
				)
			)
		self.verpackungsanlage = self.verpackungsanlage or anlage
		self.engpass = f"{engpass} ({flt(kg_h, 1):g} kg/h)"
		self.dauer_stunden = flt(self.menge_kg / kg_h, 2)
		if self.kundenauftrag:
			self.liefertermin = frappe.db.get_value("Sales Order", self.kundenauftrag, "delivery_date")
		vorher = self.get_doc_before_save()
		if vorher and vorher.status in ("Läuft", "Fertig", "Abgebrochen"):
			geaendert = [f for f in FEST_AB_START if str(vorher.get(f) or "") != str(self.get(f) or "")]
			if geaendert:
				frappe.throw(
					_(
						"Auftrag läuft bereits oder ist abgeschlossen: {0} kann nicht mehr geändert werden."
					).format(", ".join(self.meta.get_label(f) for f in geaendert))
				)

	def on_trash(self):
		if self.status != "Geplant":
			frappe.throw(_("Nur geplante Aufträge können gelöscht werden. Sonst bitte abbrechen."))
