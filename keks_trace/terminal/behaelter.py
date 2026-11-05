"""Silo leer melden und Behälter reinigen."""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from keks_trace.anfrage import einmalig
from keks_trace.terminal.basis import _darf, _fehler, _meldungen, _station
from keks_trace.terminal.scan import aufloesen


@frappe.whitelist()
@einmalig
def silo_leer(station: str, silo: str) -> dict:
	from keks_trace.silo import leermeldung

	s = _station(station)
	_darf(s, "silo")
	erg = leermeldung(silo, bemerkung=_("Leermeldung am Terminal {0}").format(s.name))
	if erg.get("ausbuchung"):
		frappe.db.set_value("Stock Entry", erg["ausbuchung"], "kt_station", s.name)
	erg["hinweise"] = _meldungen()
	return erg


@frappe.whitelist()
@einmalig
def behaelter_reinigung(station: str, code: str, gereinigt=1) -> dict:
	"""Behälter zur Reinigung geben (gereinigt=0) oder als gereinigt melden (gereinigt=1, dann wieder frei).

	Nur leere Behälter. Gesperrte bleiben gesperrt (Freigabe nur durch die QS im Büro).
	Die Meldung „gereinigt“ wird mit Zeit und Station am Behälter gespeichert; die Historie führt Frappe.
	"""
	s = _station(station)
	r = aufloesen(code)
	if r["typ"] != "behaelter":
		_fehler(_("{0} ist kein Behälter.").format(code))
	if r["behaelter_typ"] == "Gebinde":
		_fehler(
			_("{0} ist ein Gebinde vom Wareneingang, es wird nicht gereinigt und wiederverwendet.").format(
				code
			)
		)
	if r.get("charge"):
		_fehler(_("Behälter {0} enthält noch Charge {1}. Erst leeren.").format(code, r["charge"]))
	if r["status"] == "Gesperrt":
		_fehler(_("Behälter {0} ist gesperrt. Freigabe nur durch die QS.").format(code))
	t = frappe.get_doc("Produkttraeger", r["behaelter"])
	if cint(gereinigt):
		t.status = "Frei"
		t.gereinigt_am = now_datetime()
		t.gereinigt_station = s.name
	else:
		t.status = "Reinigung"
	t.save(ignore_permissions=True)
	return {"behaelter": t.name, "status": t.status, "gereinigt_am": t.gereinigt_am and str(t.gereinigt_am)}
