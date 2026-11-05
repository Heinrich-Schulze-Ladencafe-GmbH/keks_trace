"""Paletten: Inhalt aus den Paletten-Bewegungen, Füllung, Status, Bestand je Los, Etikett aktuell?"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, formatdate, now_datetime

from keks_trace.palette.basis import AKTIV, EPS, VERSANDKARTON, _fehler
from keks_trace.palette.einheit import einheiten, faktor, zerlegen


def fuellung(palette: str, pos=None) -> dict | None:
	"""Wie voll ist die Palette? Anteil je Artikel nach „Palette“-Umrechnung am Artikel."""
	pos = inhalt(palette) if pos is None else pos
	anteil, ohne = 0.0, False
	for x in pos:
		f = next((e["faktor"] for e in einheiten(x["artikel"], alle=True) if e["einheit"] == "Palette"), None)
		if not f:
			ohne = True
			continue
		anteil += x["menge"] / f
	if ohne or not pos:
		return None
	artikel = {x["artikel"] for x in pos}
	text = None
	if len(artikel) == 1:
		a = next(iter(artikel))
		karton = faktor(a, "Karton") if any(e["einheit"] == "Karton" for e in einheiten(a)) else None
		voll = faktor(a, "Palette")
		if karton:
			text = f"{flt(sum(x['menge'] for x in pos) / karton, 2):g} von {flt(voll / karton, 2):g} Karton"
	return {"anteil": flt(anteil, 4), "voll": anteil >= 1 - 1e-6, "ueber": anteil > 1 + 1e-6, "text": text}


def inhalt(palette: str) -> list[dict]:
	"""Aktueller Inhalt je Los und Einheit."""
	zeilen = frappe.db.sql(
		"""
		select charge, artikel, einheit,
			sum(if(richtung = 'Zugang', anzahl, -anzahl)) as anzahl,
			sum(if(richtung = 'Zugang', menge, -menge)) as menge
		from `tabPaletten Bewegung`
		where palette = %s
		group by charge, artikel, einheit
		order by min(zeitpunkt), charge
		""",
		palette,
		as_dict=True,
	)
	ergebnis = []
	for z in zeilen:
		if flt(z.anzahl) <= EPS:
			continue
		b = frappe.db.get_value("Batch", z.charge, ["expiry_date", "kt_status", "kt_los"], as_dict=True) or {}
		ergebnis.append(
			{
				"charge": z.charge,
				# Los wie auf Beutel und Karton (Fertigware); sonst die Charge selbst
				"los": b.get("kt_los") or z.charge,
				"artikel": z.artikel,
				"name": frappe.get_cached_value("Item", z.artikel, "item_name"),
				"einheit": z.einheit,
				"anzahl": flt(z.anzahl, 3),
				"anzahl_text": f"{flt(z.anzahl, 3):g}".replace(".", ","),
				"menge": flt(z.menge, 3),
				"mhd": formatdate(b.get("expiry_date")) if b.get("expiry_date") else None,
				"mhd_datum": b.get("expiry_date"),
				"gesperrt": b.get("kt_status") == "Gesperrt",
			}
		)
	return ergebnis


def auf_paletten(charge: str, ohne_beleg: str | None = None) -> float:
	"""Menge (Lagereinheit) eines Loses, die aktuell auf Paletten steht."""
	bedingung = "and ifnull(beleg, '') != %(ohne)s" if ohne_beleg else ""
	return flt(
		frappe.db.sql(
			f"""
			select sum(if(richtung = 'Zugang', menge, -menge)) from `tabPaletten Bewegung`
			where charge = %(charge)s {bedingung}
			""",
			{"charge": charge, "ohne": ohne_beleg},
		)[0][0]
	)


def lagerbestand(charge: str) -> float:
	return flt(
		frappe.db.sql(
			"""
			select sum(sbe.qty) from `tabSerial and Batch Entry` sbe
			join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
			where sbe.batch_no = %s and sbb.is_cancelled = 0 and sbb.docstatus = 1
			""",
			charge,
		)[0][0]
	)


def lose(charge: str) -> float:
	"""Menge eines Loses am Lager, die auf keiner Palette steht."""
	return flt(lagerbestand(charge) - auf_paletten(charge), 6)


def stand(palette: str, pos=None) -> str:
	"""Fingerabdruck des Inhalts (Los, Anzahl, Einheit) zum Vergleich mit dem gedruckten Etikett."""
	pos = inhalt(palette) if pos is None else pos
	text = "|".join(f"{x['charge']}:{flt(x['anzahl'], 3):g}:{x['einheit']}" for x in pos)
	k = kartons(palette)
	return text + ("|K:" + ",".join(sorted(k)) if k else "")


def etikett_gedruckt(palette: str) -> None:
	"""Beim Druck festhalten, welchen Inhalt das Etikett zeigt (Neudruck nötig, wenn er sich ändert)."""
	frappe.db.set_value(
		"Palette",
		palette,
		{"etikett_stand": stand(palette), "etikett_gedruckt": now_datetime()},
		update_modified=False,
	)


def etikett_aktuell(palette: str, pos=None) -> bool | None:
	"""None = noch nie gedruckt; sonst ob das Etikett zum Inhalt passt."""
	gedruckt, alt = frappe.db.get_value("Palette", palette, ["etikett_gedruckt", "etikett_stand"])
	if not gedruckt:
		return None
	return (alt or "") == stand(palette, pos)


def info(palette: str) -> dict:
	p = frappe.get_doc("Palette", palette)
	pos = inhalt(palette)
	karton_liste = []
	for k in kartons(palette):
		kp = inhalt(k)
		karton_liste.append({"nve": k, "inhalt": _summe_text(kp), "menge": flt(sum(x["menge"] for x in kp), 3),
		                     "positionen": kp})  # fmt: skip
	gesamt = _zusammen(pos + [x for k in karton_liste for x in k["positionen"]])
	summe = _summe_text(pos)
	if karton_liste:
		summe = ", ".join(
			x
			for x in (f"{len(karton_liste)} Versandkarton" + ("s" if len(karton_liste) != 1 else ""), summe)
			if x
		)
	return {
		"etikett_aktuell": etikett_aktuell(palette, pos),
		"nve": p.name,
		"art": p.typ,
		"versandkarton": p.typ == VERSANDKARTON,
		"status": p.status,
		"kunde": p.kunde,
		"lieferschein": p.lieferschein,
		"test": bool(p.test_nve),
		"positionen": pos,
		# Versandkartons auf dieser Palette (je mit eigener NVE) und alles zusammen (für das Etikett)
		"versandkartons": karton_liste,
		"positionen_gesamt": gesamt,
		"auf_palette": p.get("auf_palette") if p.typ == VERSANDKARTON and p.status in AKTIV else None,
		"gewicht_kg": flt(p.get("gewicht_kg")) or None,
		"sendungsnummer": p.get("sendungsnummer"),
		"kartons": summe,
		"menge": flt(sum(x["menge"] for x in gesamt), 3),
		"fuellung": fuellung(palette, pos) if not karton_liste else None,
	}


def _zusammen(pos: list[dict]) -> list[dict]:
	"""Positionen gleicher Charge und Einheit zusammenfassen (Palette mit Versandkartons: Etikett, Übersicht)."""
	je = {}
	for x in pos:
		k = (x["charge"], x["einheit"])
		if k in je:
			je[k] = {
				**je[k],
				"anzahl": flt(je[k]["anzahl"] + x["anzahl"], 3),
				"menge": flt(je[k]["menge"] + x["menge"], 3),
			}
			je[k]["anzahl_text"] = f"{je[k]['anzahl']:g}".replace(".", ",")
		else:
			je[k] = dict(x)
	return list(je.values())


def kartons(palette: str) -> list[str]:
	"""Versandkartons, die gerade auf dieser Palette stehen (im Lager)."""
	return frappe.get_all(
		"Palette",
		filters={"auf_palette": palette, "typ": VERSANDKARTON, "status": ["in", AKTIV]},
		pluck="name",
		order_by="creation",
	)


def _summe_text(pos):
	"""„12 Karton“; angebrochene Kartons (nach Verbrauch von der Palette) als „31 Karton + 18 Stk“."""
	je, angebrochen = defaultdict(float), []
	for x in pos:
		if abs(x["anzahl"] - round(x["anzahl"])) > 1e-6:
			angebrochen.append(zerlegen(x["artikel"], x["menge"]))
		else:
			je[x["einheit"]] += x["anzahl"]
	return ", ".join([f"{flt(n, 3):g} {e}".replace(".", ",") for e, n in je.items()] + angebrochen)


def _status_pruefen(palette):
	p = frappe.get_doc("Palette", palette)
	if not inhalt(palette) and not kartons(palette) and p.status in AKTIV:
		frappe.db.set_value("Palette", palette, "status", "Leer")


def _offen(palette):
	status = frappe.db.get_value("Palette", palette, "status")
	if status is None:
		_fehler(_("Palette {0} gibt es nicht.").format(palette))
	if status == "Leer":
		frappe.db.set_value("Palette", palette, "status", "Offen")
	elif status != "Offen":
		_fehler(_("Palette {0} ist {1}. Erst wieder öffnen.").format(palette, status.lower()))
