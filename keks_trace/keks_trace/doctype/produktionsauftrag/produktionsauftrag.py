import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

FEST_AB_START = ("linie", "artikel", "menge", "einheit", "kundenauftrag")


class Produktionsauftrag(Document):
	def validate(self):
		from keks_trace import palette
		from keks_trace.utils import versandfaehig

		if not versandfaehig(self.artikel):  # Fertigware oder lose Ware im Karton (z. B. Herzen-Rohlinge)
			frappe.throw(
				_(
					"Ein Produktionsauftrag ist für Fertigware oder lose Ware im Karton. {0} ist keins von beiden."
				).format(self.artikel)
			)
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
		from keks_trace.planung import einheit_text

		self.engpass = f"{engpass} ({flt(kg_h, 1):g} {einheit_text(self.artikel)}/h)"
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
