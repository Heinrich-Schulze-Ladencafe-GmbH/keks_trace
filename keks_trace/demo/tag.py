"""Demo-Tag: jeden Morgen ein sauberer Demostand, alle Daten relativ zu heute. Dazu das Drehbuch unter /demo.

	bench --site <site> execute keks_trace.demo.tag.vorbereiten

Was vorbereitet wird:
1. Zuckerguss-Tank leeren und frisch anmischen (Haltbarkeit 2 Tage, sonst blockiert alter Guss das Garnieren).
2. Herzen-Stammdaten, Kundenaufträge und Vorrat auffüllen (demo_herzen.anlegen).
3. Eine offene Bestellung Puderzucker für heute: der Wareneingang wird in der Demo live gebucht.
4. Ein Herz komplett bis zum Kunden (demo_herzen.durchlauf): daran zeigt die QS den Rückruf im Netzbild.

Läuft nur auf Demo- und Entwicklungssystemen (Marke der Testserver-Einrichtung oder developer_mode), sonst
bricht er ab. Ergebnis steht unter dem Schlüssel `kt_demo_stand` und auf der Seite /demo.
"""

import json
import os

import frappe
from frappe import _
from frappe.utils import add_days, flt, now_datetime, nowdate

from keks_trace.demo import herzen as demo_herzen
from keks_trace.utils import demo_commit, regel_nur_hinweis

STAND = "kt_demo_stand"
BESTELLUNG_ARTIKEL = "HZ-PUDERZUCKER"
BESTELLUNG_MENGE = 100
TANK = "Zuckerguss Herzenboden"
HINWEIS = "Schleife rot, Etikett mit Jahreszahl 2026"


def erlaubt() -> bool:
	"""Demo nur auf Testsystemen: Marke der Testserver-Einrichtung, developer_mode oder im Test."""
	marke = frappe.get_site_path("private", ".kt_demo_fertig")
	return bool(frappe.flags.in_test or frappe.conf.get("developer_mode") or os.path.exists(marke))


def _tank_leeren() -> None:
	"""Tank leer melden, wie jeden Morgen in der Produktion. Vor allem anderen: alter Guss blockiert das Garnieren."""
	from keks_trace import silo

	if frappe.db.exists("Silo", TANK):
		silo.leermeldung(TANK, bemerkung="Demo-Tag: Tank morgens leer")


def _guss_frisch() -> str | None:
	"""Mindestens 5 kg Guss von heute im Tank; sonst 10 kg anmischen."""
	from keks_trace import terminal

	if not frappe.db.exists("Silo", TANK):
		return None
	lager = frappe.db.get_value("Silo", TANK, "warehouse")
	if demo_herzen._bestand("HZ-GLASUR", lager) >= 5:
		return None
	pz = demo_herzen._charge_mit("Herzen Garnieren", "HZ-PUDERZUCKER", 9.5)
	ew = demo_herzen._charge_mit("Herzen Garnieren", "HZ-EIWEISS", 0.5)
	return terminal.herstellen(
		"Herzen Garnieren",
		"HZ-GLASUR",
		[{"code": pz, "menge": 9.5}, {"code": ew, "menge": 0.5}],
	)["charge"]


def _bestellung(ctx) -> str:
	"""Offene Bestellung Puderzucker mit Liefertermin heute; vorhandene offene wird weiter genommen."""
	from keks_trace import terminal

	for b in terminal._bestellungen(BESTELLUNG_ARTIKEL):
		if b["lieferant"] == ctx.lieferant and b["offen"] >= BESTELLUNG_MENGE / 2:
			return b["bestellung"]
	lager = frappe.db.get_value("Terminal Station", "Lager", "rohstofflager")
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": ctx.lieferant,
			"company": ctx.company,
			"transaction_date": add_days(nowdate(), -3),
			"schedule_date": nowdate(),
			"items": [
				{
					"item_code": BESTELLUNG_ARTIKEL,
					"qty": BESTELLUNG_MENGE,
					"rate": 1.1,
					"schedule_date": nowdate(),
					"warehouse": lager,
				}
			],
		}
	)
	po.insert()
	po.submit()
	return po.name


def _vorhandener_durchlauf() -> dict | None:
	"""Wurde heute schon ein Herz bis zum Kunden gebracht? Dann nicht noch einmal."""
	alt = stand()
	if (
		alt.get("datum") == nowdate()
		and alt.get("durchlauf")
		and frappe.db.exists("Delivery Note", alt["durchlauf"].get("lieferschein"))
	):
		return alt["durchlauf"]
	return None


@frappe.whitelist()
def vorbereiten(neu: int = 0) -> dict:
	"""Demostand für heute. neu=1: auch dann ein neues Herz bis zum Kunden, wenn es heute schon eins gibt."""
	frappe.only_for("System Manager")
	if not erlaubt():
		frappe.throw(_("Der Demo-Tag läuft nur auf einem Test- oder Demosystem."))
	with regel_nur_hinweis("fefo_rohstoffe"):
		_tank_leeren()
		ctx = demo_herzen.anlegen(vorrat=1)
		guss = _guss_frisch()
		bestellung = _bestellung(ctx)
		durchlauf = None if int(neu) else _vorhandener_durchlauf()
		if not durchlauf:
			d = demo_herzen.durchlauf("9", 100)
			durchlauf = {k: d[k] for k in ("los", "charge", "palette", "lieferschein", "puderzucker")}
	auftrag = ctx.herz_auftrag
	if not frappe.db.get_value("Sales Order", auftrag, "kt_hinweis_produktion"):
		frappe.db.set_value("Sales Order", auftrag, "kt_hinweis_produktion", HINWEIS, update_modified=False)
	ergebnis = {
		"datum": nowdate(),
		"zeit": now_datetime().strftime("%d.%m.%Y %H:%M"),
		"kundenauftrag": auftrag,
		"kunde": frappe.db.get_value("Sales Order", auftrag, "customer_name"),
		"bestellung": bestellung,
		"bestellung_artikel": BESTELLUNG_ARTIKEL,
		"lieferant": ctx.lieferant,
		"guss": guss,
		"durchlauf": durchlauf,
		"kunde_durchlauf": frappe.db.get_value("Delivery Note", durchlauf["lieferschein"], "customer_name"),
	}
	frappe.db.set_default(STAND, json.dumps(ergebnis))
	demo_commit()
	return ergebnis


@frappe.whitelist()
def starten(neu: int = 0) -> dict:
	"""Von der Seite /demo: im Hintergrund vorbereiten (dauert ein bis zwei Minuten)."""
	frappe.only_for("System Manager")
	if not erlaubt():
		frappe.throw(_("Der Demo-Tag läuft nur auf einem Test- oder Demosystem."))
	frappe.cache.set_value("kt_demo_laeuft", now_datetime().strftime("%H:%M"), expires_in_sec=900)
	frappe.enqueue("keks_trace.demo.tag._im_hintergrund", queue="long", timeout=1500, neu=int(neu))
	return {"laeuft": True}


def _im_hintergrund(neu: int = 0):
	try:
		vorbereiten(neu)
		frappe.cache.set_value("kt_demo_fehler", None)
	except Exception as e:
		frappe.db.rollback()
		frappe.cache.set_value("kt_demo_fehler", str(e)[:500], expires_in_sec=3600)
		frappe.log_error(title="Demo-Tag vorbereiten")
	finally:
		frappe.cache.delete_value("kt_demo_laeuft")


@frappe.whitelist()
def stand() -> dict:
	"""Was heute für die Demo vorbereitet ist (leer, wenn noch nichts)."""
	try:
		s = json.loads(frappe.db.get_default(STAND) or "{}")
	except ValueError:
		s = {}
	s["heute"] = s.get("datum") == nowdate()
	s["laeuft"] = frappe.cache.get_value("kt_demo_laeuft")
	s["fehler"] = frappe.cache.get_value("kt_demo_fehler")
	s["erlaubt"] = erlaubt()
	if s.get("bestellung"):
		from keks_trace import terminal

		offen = next(
			(
				b
				for b in terminal._bestellungen(s["bestellung_artikel"])
				if b["bestellung"] == s["bestellung"]
			),
			None,
		)
		s["bestellung_offen"] = flt(offen["offen"], 3) if offen else 0
	return s


def morgens():
	"""Täglich (Scheduler): auf Demosystemen den Stand für den Tag vorbereiten. Sonst nichts."""
	marke = frappe.get_site_path("private", ".kt_demo_fertig")
	if not os.path.exists(marke):
		return
	frappe.set_user("Administrator")
	try:
		vorbereiten()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Demo-Tag morgens")
