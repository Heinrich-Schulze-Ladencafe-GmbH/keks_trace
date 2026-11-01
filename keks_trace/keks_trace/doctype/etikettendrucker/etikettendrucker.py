import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from keks_trace.etiketten import ARTEN, ARTNAMEN, zu_klein

# IPv4 oder Rechnername (Buchstaben, Ziffern, Punkt, Bindestrich); keine Leerzeichen, kein Schema, kein Port
ADRESSE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")


class Etikettendrucker(Document):
	def validate(self):
		self.adresse = (self.adresse or "").strip()
		if "://" in self.adresse or ":" in self.adresse or not ADRESSE.match(self.adresse):
			frappe.throw(_("Adresse bitte nur als IP-Adresse oder Rechnername, ohne http:// und ohne Port."))
		if not 1 <= cint(self.port) <= 65535:
			frappe.throw(_("Der Port muss zwischen 1 und 65535 liegen (meist 9100)."))
		if not (25 <= flt(self.etikett_breite) <= 170 and 20 <= flt(self.etikett_hoehe) <= 400):
			frappe.throw(_("Rollengröße bitte in mm: Breite 25 bis 170, Höhe 20 bis 400."))
		# Wird die Rolle kleiner: passt sie noch zu allem, wofür der Drucker an Terminals eingetragen ist?
		if not self.is_new():
			fehler = sorted(
				{
					f"{z['station']}: {meldung}"
					for z in genutzt(self.name)
					if (meldung := zu_klein(z["art"], self.etikett_breite, self.etikett_hoehe))
				}
			)
			if fehler:
				frappe.throw("<br>".join([_("Diese Rolle ist zu klein für:"), *fehler]))

	def onload(self):
		self.set_onload("genutzt", genutzt(self.name))


def genutzt(drucker: str) -> list[dict]:
	"""Welche Terminals den Drucker für welche Etiketten nutzen."""
	zeilen = []
	for art, feld in ARTEN.items():
		for s in frappe.get_all(
			"Terminal Station", filters={feld: drucker}, fields=["name", "aktiv"], order_by="name"
		):
			zeilen.append({"station": s.name, "aktiv": s.aktiv, "art": art, "etikett": _(ARTNAMEN[art])})
	return zeilen
