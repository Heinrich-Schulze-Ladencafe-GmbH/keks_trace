"""Sperren und Freigeben von Chargen, Rückrufsperre (IFS Food 5.11, 4.18).

- Artikel mit „Freigabe vor Verwendung“: jede neue Charge ist gesperrt, bis die QS sie freigibt
  (Wareneingangsprüfung, Freigabe loser Ware vor dem Verpacken).
- Gesperrte Chargen können nicht verarbeitet, umgefüllt oder ausgeliefert werden.
  Umlagern (z. B. ins Sperrlager) und Ausbuchen (Entsorgung) bleiben möglich.
- Rückrufsperre: sperrt eine Charge und alle Chargen, in die sie eingeflossen ist.
- Jede Sperre und Freigabe wird unveränderbar in `Chargen Sperre` protokolliert.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from keks_trace.utils import zeilen_chargen

QS_ROLLEN = {"Quality Manager", "System Manager"}

# Diese Buchungsarten verarbeiten oder liefern Ware und sind für gesperrte Chargen verboten.
GESPERRTE_ZWECKE = ("Manufacture", "Repack", "Material Transfer for Manufacture")


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def batch_before_insert(doc, method=None):
	if frappe.get_cached_value("Item", doc.item, "kt_freigabe_pflicht"):
		doc.kt_status = "Gesperrt"
		doc.kt_sperrgrund = _("Freigabe durch die QS ausstehend")
	elif not doc.get("kt_status"):
		doc.kt_status = "Freigegeben"


def batch_after_insert(doc, method=None):
	if doc.kt_status == "Gesperrt":
		_protokoll(doc.name, doc.item, "Sperren", doc.kt_sperrgrund, None)


def pruefe_stock_entry(doc):
	if doc.purpose not in GESPERRTE_ZWECKE:
		return
	for r in doc.items:
		if not r.s_warehouse:
			continue
		_pruefe_zeile(r)


def pruefe_lieferung(doc, method=None):
	if doc.get("is_return"):
		return
	for r in doc.items:
		_pruefe_zeile(r)


def _pruefe_zeile(r):
	for charge, _menge in zeilen_chargen(r):
		status, grund = frappe.db.get_value("Batch", charge, ["kt_status", "kt_sperrgrund"]) or (None, None)
		if status == "Gesperrt":
			frappe.throw(
				_("Charge {0} ({1}) ist gesperrt: {2}").format(
					frappe.bold(charge), r.item_code, grund or "-"
				),
				title=_("Charge gesperrt"),
			)


# ---------------------------------------------------------------------------
# Aktionen (QS)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def sperren(charge: str, grund: str, vorgang: str | None = None) -> dict:
	_pruefe_rolle()
	return _setze(charge, "Gesperrt", grund, vorgang)


@frappe.whitelist()
def freigeben(charge: str, bemerkung: str) -> dict:
	_pruefe_rolle()
	return _setze(charge, "Freigegeben", bemerkung, None)


@frappe.whitelist()
def rueckruf_sperre(charge: str, grund: str) -> dict:
	"""Sperrt die Charge und alle Chargen, in die sie eingeflossen ist. Gibt Chargen und Kunden zurück."""
	from keks_trace.trace import kunden, vorwaerts

	_pruefe_rolle()
	if not grund:
		frappe.throw(_("Bitte einen Grund für den Rückruf angeben."))
	vorgang = "RR-" + now_datetime().strftime("%Y%m%d-%H%M%S")
	betroffen = [charge] + [z["charge"] for z in vorwaerts(charge)]
	gesperrt = []
	for c in betroffen:
		if frappe.db.get_value("Batch", c, "kt_status") != "Gesperrt":
			_setze(c, "Gesperrt", _("Rückruf {0}: {1}").format(vorgang, grund), vorgang)
		gesperrt.append(
			{
				"charge": c,
				"artikel": frappe.db.get_value("Batch", c, "item"),
				"bestand": frappe.db.get_value("Batch", c, "batch_qty"),
			}
		)
	from keks_trace.palette import paletten_fuer
	from keks_trace.trace import lagerverkauf

	return {
		"vorgang": vorgang,
		"chargen": gesperrt,
		"kunden": kunden(betroffen),
		"paletten": [p for p in paletten_fuer(betroffen) if p.status in ("Offen", "Geschlossen")],
		"lagerverkauf": [z for z in lagerverkauf(betroffen) if z.bestand > 1e-6],
	}


def _pruefe_rolle():
	if not QS_ROLLEN & set(frappe.get_roles()):
		frappe.throw(_("Nur die QS darf Chargen sperren oder freigeben."), frappe.PermissionError)


def _setze(charge, status, grund, vorgang):
	if not grund:
		frappe.throw(_("Bitte einen Grund bzw. eine Bemerkung angeben."))
	item = frappe.db.get_value("Batch", charge, "item")
	if not item:
		frappe.throw(_("Charge {0} existiert nicht.").format(charge))
	frappe.db.set_value(
		"Batch",
		charge,
		{"kt_status": status, "kt_sperrgrund": grund if status == "Gesperrt" else None},
	)
	_protokoll(charge, item, "Sperren" if status == "Gesperrt" else "Freigeben", grund, vorgang)
	return {"charge": charge, "status": status}


def _protokoll(charge, item, aktion, grund, vorgang):
	doc = frappe.get_doc(
		{
			"doctype": "Chargen Sperre",
			"charge": charge,
			"artikel": item,
			"aktion": aktion,
			"grund": grund,
			"vorgang": vorgang,
			"zeitpunkt": now_datetime(),
			"nutzer": frappe.session.user,
		}
	)
	doc.flags.kt_vom_system = True
	doc.insert(ignore_permissions=True)
