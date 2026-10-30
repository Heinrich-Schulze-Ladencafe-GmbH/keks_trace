"""Unveränderbarkeit der Aufzeichnungen (IFS Food 2.1.2.1).

- Genealogie, Behälterhistorie und Sperrprotokoll werden nur vom System geschrieben und
  können von niemandem geändert oder gelöscht werden (auch nicht vom Administrator).
- Gebuchte oder stornierte Belege werden nicht gelöscht. Korrektur nur per Storno.
- Chargen mit Historie werden nicht gelöscht. Herstell- und Verfallsdatum darf nur die QS ändern;
  die Änderung wird protokolliert (Versionshistorie). Sperrstatus und vererbte Daten setzt nur das System.
"""

import frappe
from frappe import _

from keks_trace.sperre import QS_ROLLEN

SYSTEM_FELDER = ("kt_status", "kt_sperrgrund", "kt_ursprungsdatum", "kt_backtag", "kt_komponenten_mhd")
QS_FELDER = ("manufacturing_date", "expiry_date", "item")


def nur_einfuegen_validate(doc):
	if not doc.is_new():
		frappe.throw(
			_("{0} ist ein Protokoll und kann nicht geändert werden.").format(_(doc.doctype)),
			title=_("Nicht änderbar"),
		)


def nur_einfuegen_on_trash(doc):
	frappe.throw(
		_("{0} ist ein Protokoll und kann nicht gelöscht werden.").format(_(doc.doctype)),
		title=_("Nicht löschbar"),
	)


def beleg_on_trash(doc, method=None):
	if doc.docstatus != 0:
		frappe.throw(
			_(
				"Gebuchte oder stornierte Belege werden aus Gründen der Rückverfolgbarkeit nicht gelöscht. "
				"{0} {1} bleibt erhalten."
			).format(_(doc.doctype), doc.name),
			title=_("Nicht löschbar"),
		)


def batch_on_trash(doc, method=None):
	for doctype, felder in (
		("Chargen Genealogie", ("input_batch", "output_batch")),
		("Traeger Belegung", ("charge",)),
		("Chargen Sperre", ("charge",)),
		("Rueckverfolgungstest", ("charge",)),
	):
		for feld in felder:
			if frappe.db.exists(doctype, {feld: doc.name}):
				frappe.throw(
					_("Charge {0} hat eine Historie ({1}) und kann nicht gelöscht werden.").format(
						doc.name, _(doctype)
					),
					title=_("Nicht löschbar"),
				)


def batch_validate(doc, method=None):
	if doc.is_new() or doc.flags.kt_vom_system:
		return
	vorher = doc.get_doc_before_save()
	if not vorher:
		return

	for feld in SYSTEM_FELDER:
		if str(doc.get(feld) or "") != str(vorher.get(feld) or ""):
			frappe.throw(
				_(
					"{0} wird vom System gesetzt (Sperren/Freigeben bzw. beim Buchen) und kann nicht von Hand geändert werden."
				).format(doc.meta.get_label(feld)),
				title=_("Nicht änderbar"),
			)

	geaendert = [f for f in QS_FELDER if str(doc.get(f) or "") != str(vorher.get(f) or "")]
	if geaendert and _hat_historie(doc.name) and not QS_ROLLEN & set(frappe.get_roles()):
		frappe.throw(
			_("Nur die QS darf {0} einer Charge mit Historie ändern.").format(
				", ".join(doc.meta.get_label(f) for f in geaendert)
			),
			frappe.PermissionError,
		)


def _hat_historie(charge):
	return bool(
		frappe.db.exists("Chargen Genealogie", {"input_batch": charge})
		or frappe.db.exists("Chargen Genealogie", {"output_batch": charge})
	)
