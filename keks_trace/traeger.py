"""Behälter, Kisten und Paletten (Produktträger) mit Code.

Am Buchungsposten (Stock Entry Detail) steht im Feld `kt_traeger` der gescannte Träger:
- Ausgang (erzeugte Charge): der Träger wird mit dieser Charge befüllt.
- Eingang (verbrauchte Charge): aus dem Träger wird entnommen; ist er leer, wird er frei.

Der Träger kennt seinen Inhalt (Charge und Menge). Ein Teig kann so auf mehrere Behälter
verteilt sein, und jeder Behälter wird einzeln geleert.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime

from keks_trace.utils import ausgangs_zeilen, eingangs_zeilen, zeilen_chargen, zeilen_menge

TOLERANZ = 0.005  # 0,5 % Wiegetoleranz beim Entnehmen


def pruefe(doc):
	befuellt = {}
	for r in ausgangs_zeilen(doc):
		if not r.get("kt_traeger"):
			continue
		t = _traeger(r.kt_traeger)
		if t.status in ("Reinigung", "Gesperrt"):
			frappe.throw(
				_("Behälter {0} ist auf '{1}' gesetzt und kann nicht befüllt werden.").format(
					frappe.bold(t.code), _(t.status)
				),
				title=_("Behälter nicht verfügbar"),
			)
		if t.status == "Belegt" and t.charge != r.batch_no:
			frappe.throw(
				_("Behälter {0} enthält noch Charge {1} ({2}). Erst leeren, dann neu befüllen.").format(
					frappe.bold(t.code), frappe.bold(t.charge), flt(t.menge, 3)
				),
				title=_("Behälter belegt"),
			)
		if befuellt.get(t.name, r.batch_no) != r.batch_no:
			frappe.throw(_("Behälter {0} kann nicht mit zwei Chargen befüllt werden.").format(t.code))
		befuellt[t.name] = r.batch_no

	entnahme = {}
	for r in eingangs_zeilen(doc):
		if not r.get("kt_traeger"):
			continue
		t = _traeger(r.kt_traeger)
		if t.status != "Belegt" or t.charge != r.batch_no:
			frappe.throw(
				_("Im Behälter {0} liegt {1}, gescannt wurde Charge {2}.").format(
					frappe.bold(t.code),
					_("Charge {0}").format(frappe.bold(t.charge)) if t.charge else _("nichts"),
					frappe.bold(r.batch_no),
				),
				title=_("Falscher Behälter"),
			)
		entnahme[t.name] = entnahme.get(t.name, 0) + zeilen_menge(r)
		if entnahme[t.name] > flt(t.menge) * (1 + TOLERANZ) + 1e-6:
			frappe.throw(
				_("Behälter {0} enthält nur {1}, entnommen werden sollen {2}.").format(
					frappe.bold(t.code), flt(t.menge, 3), flt(entnahme[t.name], 3)
				),
				title=_("Zu viel entnommen"),
			)


def on_submit(doc, method=None):
	if doc.purpose not in ("Manufacture", "Repack"):
		return
	zeit = get_datetime(f"{doc.posting_date} {doc.posting_time}")

	for r in eingangs_zeilen(doc):
		if r.get("kt_traeger"):
			_entnehmen(r.kt_traeger, r.batch_no, zeilen_menge(r), doc.name, zeit)

	for r in ausgangs_zeilen(doc):
		if r.get("kt_traeger"):
			_befuellen(r.kt_traeger, r.batch_no, r.item_code, zeilen_menge(r), doc.name, zeit)


def on_cancel(doc, method=None):
	if doc.purpose not in ("Manufacture", "Repack"):
		return

	# Beim Storno kann ERPNext das Feld batch_no schon geleert haben: Charge aus dem Bundle holen.
	for r in ausgangs_zeilen(doc):
		if not r.get("kt_traeger"):
			continue
		bel = _offene_belegung(r.kt_traeger, _charge(r)) or frappe.db.get_value(
			"Traeger Belegung",
			{"traeger": r.kt_traeger, "stock_entry_eingang": doc.name, "offen": 1},
			["name", "menge_aktuell", "von", "artikel"],
			as_dict=True,
		)
		if not bel:
			continue
		rest = flt(bel.menge_aktuell) - zeilen_menge(r)
		if rest <= 1e-6:
			frappe.db.set_value(
				"Traeger Belegung", bel.name, {"menge_aktuell": 0, "offen": 0, "bis": get_datetime()}
			)
			_setze_traeger(r.kt_traeger, None, None, 0, None)
		else:
			frappe.db.set_value("Traeger Belegung", bel.name, "menge_aktuell", rest)
			frappe.db.set_value("Produkttraeger", r.kt_traeger, "menge", rest)

	for r in eingangs_zeilen(doc):
		if not r.get("kt_traeger"):
			continue
		t = _traeger(r.kt_traeger)
		menge = zeilen_menge(r)
		charge = _charge(r)
		bel = _offene_belegung(r.kt_traeger, charge) or frappe.db.get_value(
			"Traeger Belegung",
			{"traeger": r.kt_traeger, "stock_entry_ausgang": doc.name},
			["name", "charge", "menge_aktuell", "von", "artikel"],
			as_dict=True,
		)
		charge = charge or (bel and bel.get("charge"))
		if t.status == "Belegt" and t.charge != charge:
			frappe.throw(
				_("Storno nicht möglich: Behälter {0} ist inzwischen mit Charge {1} belegt.").format(
					t.code, t.charge
				)
			)
		if not bel:
			continue
		neu = flt(bel.menge_aktuell) + menge
		frappe.db.set_value(
			"Traeger Belegung",
			bel.name,
			{"menge_aktuell": neu, "offen": 1, "bis": None, "stock_entry_ausgang": None},
		)
		_setze_traeger(r.kt_traeger, charge, bel.artikel, neu, bel.von)


def info(code: str) -> dict:
	"""Was liegt in diesem Behälter? Für Scanner und Terminals."""
	t = _traeger(code)
	return {
		"code": t.code,
		"typ": t.typ,
		"status": t.status,
		"charge": t.charge,
		"artikel": t.artikel,
		"menge": flt(t.menge, 3),
		"belegt_seit": t.belegt_seit,
		"verfall": frappe.db.get_value("Batch", t.charge, "expiry_date") if t.charge else None,
	}


# ---------------------------------------------------------------------------


def _traeger(code):
	if not frappe.db.exists("Produkttraeger", code):
		frappe.throw(
			_("Behälter {0} ist nicht bekannt.").format(frappe.bold(code)), title=_("Unbekannter Behälter")
		)
	return frappe.db.get_value(
		"Produkttraeger",
		code,
		["name", "code", "typ", "status", "charge", "artikel", "menge", "belegt_seit"],
		as_dict=True,
	)


def _charge(row):
	if row.get("batch_no"):
		return row.batch_no
	chargen = zeilen_chargen(row)
	return chargen[0][0] if chargen else None


def _offene_belegung(traeger, charge):
	return frappe.db.get_value(
		"Traeger Belegung",
		{"traeger": traeger, "charge": charge, "offen": 1},
		["name", "menge_aktuell", "von", "artikel"],
		as_dict=True,
	)


def _entnehmen(traeger, charge, menge, stock_entry, zeit):
	bel = _offene_belegung(traeger, charge)
	if not bel:
		return
	rest = flt(bel.menge_aktuell) - menge
	if rest <= flt(bel.menge_aktuell) * TOLERANZ + 1e-6:
		frappe.db.set_value(
			"Traeger Belegung",
			bel.name,
			{"menge_aktuell": 0, "offen": 0, "bis": zeit, "stock_entry_ausgang": stock_entry},
		)
		_setze_traeger(traeger, None, None, 0, None)
	else:
		frappe.db.set_value("Traeger Belegung", bel.name, "menge_aktuell", rest)
		frappe.db.set_value("Produkttraeger", traeger, "menge", rest)


def _befuellen(traeger, charge, artikel, menge, stock_entry, zeit):
	bel = _offene_belegung(traeger, charge)
	if bel:
		neu = flt(bel.menge_aktuell) + menge
		frappe.db.set_value("Traeger Belegung", bel.name, "menge_aktuell", neu)
		frappe.db.set_value("Produkttraeger", traeger, "menge", neu)
		return
	frappe.get_doc(
		{
			"doctype": "Traeger Belegung",
			"traeger": traeger,
			"charge": charge,
			"artikel": artikel,
			"offen": 1,
			"menge_eingang": menge,
			"menge_aktuell": menge,
			"von": zeit,
			"stock_entry_eingang": stock_entry,
		}
	).insert(ignore_permissions=True)
	_setze_traeger(traeger, charge, artikel, menge, zeit)


def _setze_traeger(traeger, charge, artikel, menge, seit):
	frappe.db.set_value(
		"Produkttraeger",
		traeger,
		{
			"status": "Belegt" if charge else "Frei",
			"charge": charge,
			"artikel": artikel,
			"menge": menge,
			"belegt_seit": seit,
		},
	)
