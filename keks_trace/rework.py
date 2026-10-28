"""Rework-Regeln, geprüft bei jeder Fertigungs- und Umpackbuchung.

Blockierend:
- Rework darf nur in Grundteig oder veredelten Teig eingesetzt werden
  (oder in denselben Rework-Artikel umgefüllt werden).
- Für die Kombination Rework-Artikel -> Teig muss eine aktive Rework-Regel existieren (Rework-Matrix).
- Das Rework darf keine Allergene enthalten, die der Zielteig nicht hat (auch wenn eine Regel existiert).
- Der Rework-Anteil am Teig darf das Maximum der Regel nicht überschreiten.
- Abgelaufene Rework-Chargen sind gesperrt (siehe keks_trace.pruefungen, Verfall = Ursprungsdatum
  + Haltbarkeit des Rework-Artikels).

Nur Hinweis (FIFO): es gibt eine ältere, noch verfügbare Rework-Charge desselben Artikels.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate

from keks_trace.install import REWORK_ZIELE
from keks_trace.utils import (
	allergene,
	artikel_stufe,
	ausgangs_zeilen,
	eingangs_zeilen,
	zeilen_chargen,
	zeilen_menge,
)


def pruefe(doc):

	eingaenge = eingangs_zeilen(doc)
	ausgaenge = [r for r in ausgangs_zeilen(doc) if r.is_finished_item] or ausgangs_zeilen(doc)
	if not eingaenge or not ausgaenge:
		return

	rework_zeilen = [r for r in eingaenge if artikel_stufe(r.item_code) == "Rework"]
	if not rework_zeilen:
		return

	ziel = ausgaenge[0].item_code
	ziel_stufe = artikel_stufe(ziel)

	rework_menge = defaultdict(float)
	for r in rework_zeilen:
		rework_menge[r.item_code] += zeilen_menge(r)

	gesamt = sum(zeilen_menge(r) for r in eingaenge)

	for rework_artikel, menge in rework_menge.items():
		if rework_artikel == ziel:
			# Umfüllen/Zusammenführen von Rework-Behältern desselben Artikels.
			continue

		if ziel_stufe not in REWORK_ZIELE:
			frappe.throw(
				_("Rework {0} darf nur in Grundteig oder veredelten Teig, nicht in {1} ({2}).").format(
					frappe.bold(rework_artikel), frappe.bold(ziel), ziel_stufe or _("ohne Stufe")
				),
				title=_("Rework nicht zulässig"),
			)

		regel = frappe.db.get_value(
			"Rework Regel",
			{"rework_artikel": rework_artikel, "ziel_artikel": ziel, "aktiv": 1},
			["name", "max_anteil_prozent"],
			as_dict=True,
		)
		if not regel:
			frappe.throw(
				_(
					"Rework {0} ist für {1} nicht zugelassen. Es gibt keine aktive Rework-Regel (Rework-Matrix)."
				).format(frappe.bold(rework_artikel), frappe.bold(ziel)),
				title=_("Rework nicht zulässig"),
			)

		_pruefe_allergene(rework_artikel, ziel)

		anteil = menge / gesamt * 100 if gesamt else 0
		if anteil > flt(regel.max_anteil_prozent) + 1e-9:
			zulaessig = gesamt * flt(regel.max_anteil_prozent) / 100
			frappe.throw(
				_(
					"Rework-Anteil {0} % überschreitet das Maximum von {1} % für {2}. "
					"Bei {3} kg Gesamtmenge sind höchstens {4} kg Rework zulässig."
				).format(
					flt(anteil, 1),
					flt(regel.max_anteil_prozent),
					frappe.bold(ziel),
					flt(gesamt, 2),
					flt(zulaessig, 2),
				),
				title=_("Zu viel Rework"),
			)

	_fifo_hinweis(doc, rework_zeilen)


def _pruefe_allergene(rework_artikel: str, ziel: str):
	rework_gruppe = frappe.get_cached_value("Item", rework_artikel, "kt_allergengruppe")
	ziel_gruppe = frappe.get_cached_value("Item", ziel, "kt_allergengruppe")
	zusaetzlich = allergene(rework_gruppe) - allergene(ziel_gruppe)
	if zusaetzlich:
		frappe.throw(
			_("Rework {0} enthält Allergene, die {1} nicht enthält: {2}. Einsatz gesperrt.").format(
				frappe.bold(rework_artikel),
				frappe.bold(ziel),
				", ".join(sorted(a.capitalize() for a in zusaetzlich)),
			),
			title=_("Allergenkonflikt"),
		)


def _fifo_hinweis(doc, rework_zeilen):
	"""Warnung, wenn eine ältere Rework-Charge desselben Artikels noch Bestand hat."""
	warnungen = []
	verwendet = {c for r in rework_zeilen for c, _m in zeilen_chargen(r)}
	for r in rework_zeilen:
		for charge, _menge in zeilen_chargen(r):
			datum = frappe.db.get_value("Batch", charge, "manufacturing_date")
			if not datum:
				continue
			for a in _aeltere_chargen(r.item_code, datum, verwendet, doc.posting_date):
				warnungen.append(
					_(
						"Ältere Rework-Charge {0} ({1}) ist noch verfügbar und sollte zuerst verwendet werden."
					).format(frappe.bold(a.name), formatdate(a.manufacturing_date))
				)
	doc.flags.kt_fifo_warnungen = warnungen
	for w in warnungen:
		frappe.msgprint(w, title=_("FIFO-Hinweis"), indicator="orange", alert=True)


def _aeltere_chargen(item_code, datum, verwendet, stichtag):
	return frappe.db.sql(
		"""
		select name, manufacturing_date
		from `tabBatch`
		where item = %(item)s
			and disabled = 0
			and batch_qty > 0
			and manufacturing_date < %(datum)s
			and (expiry_date is null or expiry_date >= %(stichtag)s)
			and name not in %(verwendet)s
		order by manufacturing_date asc
		""",
		{
			"item": item_code,
			"datum": datum,
			"stichtag": getdate(stichtag),
			"verwendet": tuple(verwendet) or ("",),
		},
		as_dict=True,
	)
