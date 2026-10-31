"""Bio-Mengenabgleich je Artikel und Zeitraum (Nachweis für die Öko-Kontrolle).

Je Bio-Artikel: Bestand am Anfang, Wareneingang, hergestellt, verbraucht, ausgeliefert,
Lagerverkauf, entsorgt, Bestand am Ende. Darunter: wie viel Bio-Rohware eingesetzt wurde und wie
viel Bio-Fertigware dabei herauskam.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, nowdate

from keks_trace.kennzeichnung import bio_abgleich


def execute(filters=None):
	filters = frappe._dict(filters or {})
	von = filters.von or get_first_day(add_months(nowdate(), -1))
	bis = filters.bis or get_last_day(von)
	daten = bio_abgleich(von, bis)
	return _spalten(), daten, _nachricht(daten)


def _spalten():
	def zahl(name, label):
		return {"fieldname": name, "label": label, "fieldtype": "Float", "precision": 3, "width": 110}

	return [
		{"fieldname": "artikel", "label": _("Artikel"), "fieldtype": "Link", "options": "Item", "width": 130},
		{"fieldname": "artikelname", "label": _("Bezeichnung"), "fieldtype": "Data", "width": 200},
		{"fieldname": "stufe", "label": _("Stufe"), "fieldtype": "Data", "width": 110},
		{"fieldname": "einheit", "label": _("Einheit"), "fieldtype": "Data", "width": 70},
		zahl("anfang", _("Anfang")),
		zahl("wareneingang", _("Eingang")),
		zahl("hergestellt", _("Hergestellt")),
		zahl("verbraucht", _("Verbraucht")),
		zahl("ausgeliefert", _("Ausgeliefert")),
		zahl("lagerverkauf", _("Lagerverkauf")),
		zahl("entsorgt", _("Entsorgt")),
		zahl("sonstiges", _("Sonstiges")),
		zahl("ende", _("Ende")),
	]


def _nachricht(daten):
	if not daten:
		return _("Keine Bio-Chargen im Zeitraum.")
	roh = sum(z["wareneingang"] for z in daten if z["stufe"] == "Rohstoff" and z["einheit"] == "Kg")
	eingesetzt = sum(z["verbraucht"] for z in daten if z["stufe"] == "Rohstoff" and z["einheit"] == "Kg")
	fertig = sum(z["hergestellt"] for z in daten if z["stufe"] == "Fertigware")
	raus = sum(z["ausgeliefert"] + z["lagerverkauf"] for z in daten if z["stufe"] == "Fertigware")
	return _(
		"Bio-Rohware: {0} kg eingegangen, {1} kg eingesetzt · Bio-Fertigware: {2} kg hergestellt, {3} kg verkauft"
	).format(*(f"{flt(x, 1):g}".replace(".", ",") for x in (roh, eingesetzt, fertig, raus)))
