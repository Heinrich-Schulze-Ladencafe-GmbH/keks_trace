"""Paletten: Versandkartons mit eigener NVE auf einer Palette (eine Ebene)."""

import frappe
from frappe import _
from frappe.utils import now_datetime

from keks_trace.palette.basis import AKTIV, VERSANDKARTON, _fehler
from keks_trace.palette.bestand import _offen, _status_pruefen, info, inhalt


def _zuordnung(karton, palette, richtung, station=None, beleg=None):
	frappe.get_doc(
		{"doctype": "Versandkarton Zuordnung", "karton": karton, "palette": palette, "richtung": richtung,
		 "zeitpunkt": now_datetime(), "station": station, "nutzer": frappe.session.user, "beleg": beleg}
	).insert(ignore_permissions=True)  # fmt: skip


def karton_auf_palette(karton: str, palette: str, station: str | None = None) -> dict:
	"""Versandkarton auf eine Palette stellen. Der Karton wird dabei geschlossen (sein Inhalt bleibt seiner)."""
	k = frappe.db.get_value("Palette", karton, ["typ", "status", "auf_palette"], as_dict=True)
	if not k:
		_fehler(_("Versandkarton {0} gibt es nicht.").format(karton))
	if k.typ != VERSANDKARTON:
		_fehler(
			_("{0} ist kein Versandkarton, sondern eine {1}. Bitte umpacken statt aufstellen.").format(
				karton, k.typ
			)
		)
	if frappe.db.get_value("Palette", palette, "typ") == VERSANDKARTON:
		_fehler(_("Ein Versandkarton kommt auf eine Palette, nicht in einen anderen Versandkarton."))
	if k.status not in AKTIV:
		_fehler(_("Versandkarton {0} ist {1}.").format(karton, k.status.lower()))
	if not inhalt(karton):
		_fehler(_("Versandkarton {0} ist leer.").format(karton))
	if k.auf_palette == palette:
		return info(palette)
	_offen(palette)
	if k.auf_palette:
		_zuordnung(karton, k.auf_palette, "Ab", station)
	frappe.db.set_value("Palette", karton, {"auf_palette": palette, "status": "Geschlossen"})
	_zuordnung(karton, palette, "Auf", station)
	return info(palette)


def karton_abnehmen(karton: str, station: str | None = None, beleg: str | None = None) -> None:
	"""Versandkarton von seiner Palette nehmen (er bleibt im Lager, eigene NVE)."""
	palette = frappe.db.get_value("Palette", karton, "auf_palette")
	if not palette:
		return
	frappe.db.set_value("Palette", karton, "auf_palette", None)
	_zuordnung(karton, palette, "Ab", station, beleg)
	_status_pruefen(palette)
