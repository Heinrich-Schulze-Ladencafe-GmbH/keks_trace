"""Rückverfolgungstest als Nachweis für IFS Food 4.18.2.

Beim Anlegen wird der Test automatisch ausgeführt: Rückverfolgung vorwärts und rückwärts,
Mengenbilanz für jede gefundene Charge, Zeitmessung. Ergebnis und Rohdaten werden gespeichert.
Nach dem Buchen ist das Protokoll unveränderbar; ein neuer Test ist ein neues Protokoll.
"""

import json
import time

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, formatdate, now_datetime

from keks_trace.bilanz import mengenbilanz
from keks_trace.trace import rueckverfolgung


class Rueckverfolgungstest(Document):
	def before_insert(self):
		self.ausfuehren()

	def validate(self):
		if not self.is_new() and self.has_value_changed("charge"):
			frappe.throw(
				_(
					"Die geprüfte Charge kann nach dem Test nicht geändert werden. Bitte einen neuen Test anlegen."
				)
			)

	def ausfuehren(self):
		self.gestartet = now_datetime()
		start = time.perf_counter()

		vor = rueckverfolgung(self.charge, "Vorwärts")
		rueck = rueckverfolgung(self.charge, "Rückwärts")
		chargen = (
			[self.charge] + [z["charge"] for z in vor["chargen"]] + [z["charge"] for z in rueck["chargen"]]
		)
		chargen = list(dict.fromkeys(chargen))
		bilanzen = [mengenbilanz(c) for c in chargen]

		dauer = time.perf_counter() - start
		self.beendet = now_datetime()
		self.dauer_sekunden = flt(dauer, 2)

		abweichend = [b for b in bilanzen if not b["ok"]]
		self.anzahl_vorwaerts = len(vor["chargen"])
		self.anzahl_rueckwaerts = len(rueck["chargen"])
		self.anzahl_kunden = len({k.lieferschein for k in vor.get("kunden", [])})
		self.anzahl_lieferanten = len(rueck.get("lieferanten", []))
		self.anzahl_geprueft = len(bilanzen)
		self.anzahl_abweichungen = len(abweichend)
		self.ergebnis = "Abweichung" if abweichend else "Bestanden"
		self.bericht = _bericht(self, vor, rueck, bilanzen)
		self.daten = json.dumps(
			{
				"vorwaerts": vor["chargen"],
				"rueckwaerts": rueck["chargen"],
				"kunden": vor.get("kunden", []),
				"bilanzen": bilanzen,
			},
			default=str,
			ensure_ascii=False,
			indent=1,
		)


def _bericht(test, vor, rueck, bilanzen):
	z = [
		_("Rückverfolgungstest für Charge {0}").format(test.charge),
		_("Anlass: {0}").format(test.anlass),
		_("Durchgeführt von {0} am {1}, Dauer {2} s").format(
			frappe.session.user, formatdate(test.gestartet), test.dauer_sekunden
		),
		_("Ergebnis: {0}").format(test.ergebnis),
		"",
		_("Vorwärts ({0} Chargen):").format(len(vor["chargen"])),
	]
	z += [
		f"  Gen {c['generation']}  {c['charge']}  {c.get('stufe') or ''}  {flt(c['anteil']) * 100:.2f} %"
		for c in vor["chargen"]
	]
	z += ["", _("Betroffene Lieferungen:")]
	z += [
		f"  {k.kundenname or k.kunde}  {k.lieferschein}  {formatdate(k.lieferdatum)}  {k.charge}  {flt(k.menge, 3)}"
		for k in vor.get("kunden", [])
	] or ["  -"]
	z += ["", _("Rückwärts ({0} Chargen):").format(len(rueck["chargen"]))]
	z += [
		f"  Gen {c['generation']}  {c['charge']}  {c.get('stufe') or ''}  {c.get('lieferant') or ''}"
		for c in rueck["chargen"]
	]
	z += ["", _("Mengenbilanz (Zugang / Abgang / Bestand / Differenz Lager / Differenz Genealogie):")]
	for b in bilanzen:
		markierung = "OK " if b["ok"] else "!! "
		z.append(
			f"  {markierung}{b['charge']}  {b['zugang']} / {b['abgang']} / {b['bestand']} / "
			f"{b['differenz_lager']} / {b['differenz_genealogie']} {b['einheit'] or ''}"
			+ (f"  Ausbeute {b['ausbeute_prozent']} %" if b["ausbeute_prozent"] is not None else "")
		)
		z += [f"      {a}" for a in b["abweichungen"]]
	return "\n".join(z)
