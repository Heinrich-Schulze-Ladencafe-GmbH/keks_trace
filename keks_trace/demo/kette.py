"""Demo: drei Produktionstage mit Rework und Behältern (keks_trace.demo.run), Lagerware für die Demo."""

import frappe
from frappe.utils import add_days, flt, formatdate, getdate, now_datetime, nowdate

from keks_trace import silo, sperre
from keks_trace.demo.grunddaten import silos_anlegen, stammdaten
from keks_trace.demo.helfer import buchen, liefern, neue_charge, neuer_traeger
from keks_trace.utils import demo_commit


def run(company: str | None = None, kuerzel: str | None = None):
	ctx = stammdaten(company)
	kette = drei_tage_kette(ctx, kuerzel)
	test = frappe.get_doc(
		{"doctype": "Rueckverfolgungstest", "charge": kette.mehl, "anlass": "Jährlicher Test"}
	)
	test.insert()
	test.submit()
	kette.rueckverfolgungstest = test.name
	demo_commit()
	_ausgabe(kette)
	print(f"\n== Rückverfolgungstest {test.name}: {test.ergebnis} in {test.dauer_sekunden} s\n")
	print(test.bericht)
	return kette


def drei_tage_kette(ctx, kuerzel: str | None = None, start=None) -> frappe._dict:
	"""Tag 1-3 nach dem echten Ablauf. Gibt Chargen- und Behälternamen zurück."""
	k = kuerzel or now_datetime().strftime("%y%m%d%H%M%S")
	t1 = getdate(start) if start else getdate(add_days(nowdate(), -2))
	t2, t3 = getdate(add_days(t1, 1)), getdate(add_days(t1, 2))
	c = frappe._dict(kuerzel=k, tag1=t1, tag2=t2, tag3=t3)
	c.silo = silos_anlegen(ctx, k)
	W, Z, D, T = c.silo["KT-MEHL"], c.silo["KT-ZUCKER"], c.silo["KT-DINKEL"], c.silo["KT-SIRUP"]

	# Behälter mit Code (Data Matrix)
	c.tb1 = neuer_traeger(f"TB1-{k}", "Teigbehälter")
	c.tb2 = neuer_traeger(f"TB2-{k}", "Teigbehälter")
	c.tb3 = neuer_traeger(f"TB3-{k}", "Teigbehälter")
	c.tb4 = neuer_traeger(f"TB4-{k}", "Teigbehälter")
	c.rb1 = neuer_traeger(f"RB1-{k}", "Rework-Behälter")
	c.rb2 = neuer_traeger(f"RB2-{k}", "Rework-Behälter")
	c.kl1 = neuer_traeger(f"KL1-{k}", "Kiste lose Ware")
	c.kl2 = neuer_traeger(f"KL2-{k}", "Kiste lose Ware")
	c.kl3 = neuer_traeger(f"KL3-{k}", "Kiste lose Ware")

	# Wareneingang
	c.mehl = neue_charge("KT-MEHL", f"M-{k}", add_days(t1, -10), ctx.lieferant)
	c.zucker = neue_charge("KT-ZUCKER", f"Z-{k}", add_days(t1, -30), ctx.lieferant)
	c.dinkel = neue_charge("KT-DINKEL", f"D-{k}", add_days(t1, -12), ctx.lieferant)
	c.butter = neue_charge("KT-BUTTER", f"BU-{k}", add_days(t1, -3), ctx.lieferant)
	c.nuss = neue_charge("KT-HASELNUSS", f"HN-{k}", add_days(t1, -20), ctx.lieferant)
	c.kakao = neue_charge("KT-KAKAO", f"KA-{k}", add_days(t1, -40), ctx.lieferant)
	c.schoko = neue_charge("KT-SCHOKO", f"SK-{k}", add_days(t1, -30), ctx.lieferant)
	c.folie = neue_charge("KT-FOLIE", f"F-{k}", add_days(t1, -60), ctx.lieferant)
	buchen(
		ctx,
		"Material Receipt",
		t1,
		"06:00:00",
		ausgaenge=[
			("KT-MEHL", c.mehl, 125, W),
			("KT-ZUCKER", c.zucker, 100, Z),
			("KT-DINKEL", c.dinkel, 6, D),
			("KT-BUTTER", c.butter, 400),
			("KT-HASELNUSS", c.nuss, 200),
			("KT-KAKAO", c.kakao, 50),
			("KT-SCHOKO", c.schoko, 100),
			("KT-FOLIE", c.folie, 20),
		],
	)
	# Kühlware: Wareneingangsprüfung durch die QS
	sperre.freigeben(c.butter, "Wareneingangsprüfung: Temperatur 4 °C, Verpackung unbeschädigt")

	# ---- Tag 1
	# Zuckersirup aus Silozucker in den Tank (Wasser wird nicht als Charge geführt)
	c.sirup = neue_charge("KT-SIRUP", f"SI1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"06:30:00",
		eingaenge=[("KT-ZUCKER", None, 60, Z)],
		ausgaenge=[("KT-SIRUP", c.sirup, 100, T)],
	)
	# Grundteig GT1 (100 kg) in Behälter TB1; Mehl und Zucker aus dem Silo, Charge nach FIFO
	c.gt1 = neue_charge("KT-GT-MUERBE", f"GT1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"07:00:00",
		eingaenge=[
			("KT-MEHL", None, 60, W),
			("KT-ZUCKER", None, 20, Z),
			("KT-BUTTER", c.butter, 20),
		],
		ausgaenge=[("KT-GT-MUERBE", c.gt1, 100, c.tb1)],
	)
	# Nougatfüllung selbst hergestellt
	c.nougat = neue_charge("KT-NOUGAT", f"NO1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"07:30:00",
		eingaenge=[
			("KT-ZUCKER", None, 10, Z),
			("KT-HASELNUSS", c.nuss, 10),
			("KT-KAKAO", c.kakao, 5),
			("KT-BUTTER", c.butter, 5),
		],
		ausgaenge=[("KT-NOUGAT", c.nougat, 30)],
	)
	# Veredelung V1: halber Grundteig + Haselnuss
	c.v1 = neue_charge("KT-TV-NUSS", f"V1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"08:00:00",
		eingaenge=[("KT-GT-MUERBE", c.gt1, 50, c.tb1), ("KT-HASELNUSS", c.nuss, 10)],
		ausgaenge=[("KT-TV-NUSS", c.v1, 60, c.tb2)],
	)
	# Backen
	c.bw1 = neue_charge("KT-BW-NUSS", f"BW1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"09:00:00",
		eingaenge=[("KT-TV-NUSS", c.v1, 60, c.tb2)],
		ausgaenge=[("KT-BW-NUSS", c.bw1, 50)],
	)
	# Schokoboden mit gekaufter Kuvertüre -> lose Ware in Kiste KL1
	c.wl1 = neue_charge("KT-WL-NUSS-SCHOKO", f"WL1-{k}", t1)
	buchen(
		ctx,
		"Manufacture",
		t1,
		"10:00:00",
		eingaenge=[("KT-BW-NUSS", c.bw1, 48), ("KT-SCHOKO", c.schoko, 6)],
		ausgaenge=[("KT-WL-NUSS-SCHOKO", c.wl1, 54, c.kl1)],
	)
	# Bruch nach dem Backen -> Rework R1 in Rework-Behälter RB1
	c.r1 = neue_charge("KT-RW-NUSS", f"R1-{k}", t1)
	buchen(
		ctx,
		"Repack",
		t1,
		"10:30:00",
		eingaenge=[("KT-BW-NUSS", c.bw1, 2)],
		ausgaenge=[("KT-RW-NUSS", c.r1, 2, c.rb1)],
	)

	# ---- Tag 2
	# Nachfüllen, bevor die Silos leer sind: alte und neue Charge vermischen sich
	c.mehl2 = neue_charge("KT-MEHL", f"M2-{k}", add_days(t2, -5), ctx.lieferant)
	c.zucker2 = neue_charge("KT-ZUCKER", f"Z2-{k}", add_days(t2, -20), ctx.lieferant)
	buchen(
		ctx,
		"Material Receipt",
		t2,
		"06:00:00",
		ausgaenge=[
			("KT-MEHL", c.mehl2, 1000, W),
			("KT-ZUCKER", c.zucker2, 1000, Z),
		],
	)
	# Veredelung V2: zweite Hälfte von GT1 (TB1 wird leer) + Haselnuss + Rework R1 (RB1 wird leer)
	c.v2 = neue_charge("KT-TV-NUSS", f"V2-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"07:00:00",
		eingaenge=[
			("KT-GT-MUERBE", c.gt1, 50, c.tb1),
			("KT-HASELNUSS", c.nuss, 9),
			("KT-RW-NUSS", c.r1, 2, c.rb1),
		],
		ausgaenge=[("KT-TV-NUSS", c.v2, 61, c.tb2)],
	)
	c.bw2 = neue_charge("KT-BW-NUSS", f"BW2-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"08:00:00",
		eingaenge=[("KT-TV-NUSS", c.v2, 61, c.tb2)],
		ausgaenge=[("KT-BW-NUSS", c.bw2, 51)],
	)
	c.wl2 = neue_charge("KT-WL-NUSS-SCHOKO", f"WL2-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"09:00:00",
		eingaenge=[("KT-BW-NUSS", c.bw2, 45), ("KT-SCHOKO", c.schoko, 6)],
		ausgaenge=[("KT-WL-NUSS-SCHOKO", c.wl2, 51, c.kl2)],
	)
	# Zweiter Grundteig GT2 -> Kakao-Veredelung, Teigrest wird Rework R2
	c.gt2 = neue_charge("KT-GT-MUERBE", f"GT2-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"09:30:00",
		eingaenge=[
			("KT-MEHL", None, 60, W),
			("KT-ZUCKER", None, 20, Z),
			("KT-BUTTER", c.butter, 20),
		],
		ausgaenge=[("KT-GT-MUERBE", c.gt2, 100, c.tb3)],
	)
	c.v3 = neue_charge("KT-TV-KAKAO", f"V3-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"10:00:00",
		eingaenge=[
			("KT-GT-MUERBE", c.gt2, 85, c.tb3),
			("KT-DINKEL", None, 5, D),
			("KT-KAKAO", c.kakao, 5),
			("KT-SIRUP", None, 5, T),
		],
		ausgaenge=[("KT-TV-KAKAO", c.v3, 100, c.tb4)],
	)
	c.r2 = neue_charge("KT-RW-MUERBE", f"R2-{k}", t2)
	buchen(
		ctx,
		"Repack",
		t2,
		"10:30:00",
		eingaenge=[("KT-GT-MUERBE", c.gt2, 5, c.tb3)],
		ausgaenge=[("KT-RW-MUERBE", c.r2, 5, c.rb2)],
	)
	c.bw3 = neue_charge("KT-BW-KAKAO", f"BW3-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"11:00:00",
		eingaenge=[("KT-TV-KAKAO", c.v3, 100, c.tb4)],
		ausgaenge=[("KT-BW-KAKAO", c.bw3, 85)],
	)
	# Füllen mit selbst gemachtem Nougat -> lose Ware in Kiste KL3
	c.wl3 = neue_charge("KT-WL-KAKAO-NOUGAT", f"WL3-{k}", t2)
	buchen(
		ctx,
		"Manufacture",
		t2,
		"12:00:00",
		eingaenge=[("KT-BW-KAKAO", c.bw3, 80), ("KT-NOUGAT", c.nougat, 20)],
		ausgaenge=[("KT-WL-KAKAO-NOUGAT", c.wl3, 100, c.kl3)],
	)

	# ---- Freigabe loser Ware durch die QS (KL2 wartet noch auf die Freigabe)
	sperre.freigeben(c.wl1, "Sensorik, Feuchte und Bruchanteil in Ordnung")
	sperre.freigeben(c.wl3, "Sensorik, Feuchte und Bruchanteil in Ordnung")

	# ---- Tag 3
	# Dinkelsilo ist leer: Leermeldung trennt die Chargen sauber, dann neue Lieferung
	c.leermeldung_dinkel = silo.leermeldung(D, f"{t3} 05:50:00", "Silo leergefahren")
	c.dinkel2 = neue_charge("KT-DINKEL", f"D2-{k}", add_days(t3, -4), ctx.lieferant)
	buchen(
		ctx,
		"Material Receipt",
		t3,
		"06:00:00",
		ausgaenge=[("KT-DINKEL", c.dinkel2, 500, D)],
	)
	# Neuer Grundteig GT3 mit 5 % Rework R2 (Teigrest vom Vortag)
	c.gt3 = neue_charge("KT-GT-MUERBE", f"GT3-{k}", t3)
	buchen(
		ctx,
		"Manufacture",
		t3,
		"07:00:00",
		eingaenge=[
			("KT-MEHL", None, 57, W),
			("KT-ZUCKER", None, 19, Z),
			("KT-BUTTER", c.butter, 19),
			("KT-RW-MUERBE", c.r2, 5, c.rb2),
		],
		ausgaenge=[("KT-GT-MUERBE", c.gt3, 100)],
	)
	# Verpacken aus dem Lager loser Ware (Kiste KL1 bleibt mit Rest belegt)
	c.l1 = neue_charge("KT-FW-NUSS-SCHOKO", f"L1-{k}", t3)
	buchen(
		ctx,
		"Manufacture",
		t3,
		"08:00:00",
		eingaenge=[("KT-WL-NUSS-SCHOKO", c.wl1, 40, c.kl1), ("KT-FOLIE", c.folie, 1)],
		ausgaenge=[("KT-FW-NUSS-SCHOKO", c.l1, 40)],
	)
	c.l2 = neue_charge("KT-FW-KAKAO-NOUGAT", f"L2-{k}", t3)
	buchen(
		ctx,
		"Manufacture",
		t3,
		"08:30:00",
		eingaenge=[("KT-WL-KAKAO-NOUGAT", c.wl3, 50, c.kl3), ("KT-FOLIE", c.folie, 1)],
		ausgaenge=[("KT-FW-KAKAO-NOUGAT", c.l2, 50)],
	)
	c.lieferschein = liefern(
		ctx, t3, [("KT-FW-NUSS-SCHOKO", c.l1, 30), ("KT-FW-KAKAO-NOUGAT", c.l2, 20)]
	).name
	return c


def _ausgabe(c):
	from keks_trace.trace import rueckverfolgung

	print(f"\nDemo-Kette {c.kuerzel}: Tag 1 = {formatdate(c.tag1)}, Tag 3 = {formatdate(c.tag3)}")
	for titel, charge, richtung in (
		("Rückruf Mehlcharge (vorwärts)", c.mehl, "Vorwärts"),
		("Reklamation Los L2 Kakao-Nougat (rückwärts)", c.l2, "Rückwärts"),
		("Grundteig Tag 3 (rückwärts, mit Rework)", c.gt3, "Rückwärts"),
	):
		r = rueckverfolgung(charge, richtung)
		print(f"\n== {titel}: {charge}")
		for z in r["chargen"]:
			print(
				f"  Gen {z['generation']}  {z['charge']:<20} {z.get('stufe') or '':<14} "
				f"Anteil {flt(z['anteil']) * 100:6.2f} %  hergestellt {formatdate(z.get('herstelldatum'))}"
				f"  Verfall/MHD {formatdate(z.get('verfall')) if z.get('verfall') else '-'}"
			)
		for kd in r.get("kunden", []):
			print(
				f"  -> Kunde {kd.kundenname}: Lieferschein {kd.lieferschein} am {formatdate(kd.lieferdatum)}, "
				f"{flt(kd.menge)} kg {kd.charge}"
			)

	print("\n== Silos und Tank (Bestand rechnerisch / möglicherweise noch enthalten)")
	for name in c.silo.values():
		i = silo.info(name)
		print(
			f"  {name:<22} "
			+ ", ".join(f"{b['charge']} {flt(b['menge']):g}" for b in i["bestand"])
			+ f"  | {', '.join(i['moeglich_enthalten'])}"
		)

	print("\n== Behälter")
	for code in (c.tb1, c.tb2, c.tb3, c.tb4, c.rb1, c.rb2, c.kl1, c.kl2, c.kl3):
		t = frappe.db.get_value("Produkttraeger", code, ["status", "charge", "menge"], as_dict=True)
		print(f"  {code:<20} {t.status:<8} {t.charge or '':<20} {flt(t.menge):g} kg")


@frappe.whitelist()
def lagerware() -> dict:
	"""Demo zum Umlagern: Honig Lebkuchen in drei Losen im Fertigwarenlager, eins davon auf einer Palette.

	bench --site keks.localhost execute keks_trace.demo.lagerware
	"""
	from frappe.utils import add_days, add_months, getdate, nowdate

	from keks_trace import los as los_modul
	from keks_trace import palette as paletten
	from keks_trace.demo import pilot

	ctx = pilot.anlegen()
	ergebnis = []
	for tage, kartons, auf_palette in ((60, 30, 0), (30, 42, 42), (7, 25, 0)):
		tag = getdate(add_days(nowdate(), -tage))
		los = los_modul.jwwt(tag)
		name = f"17846-{tag.isocalendar()[0]}-{los}"
		if not frappe.db.exists("Batch", name):
			charge = neue_charge("17846", name, tag)
			frappe.db.set_value(
				"Batch",
				charge,
				{"kt_los": los, "expiry_date": add_months(tag, 9), "kt_status": "Freigegeben"},
			)
			buchen(ctx, "Material Receipt", tag, "14:00:00", ausgaenge=[("17846", charge, kartons * 4.0)])
			if auf_palette:
				p = paletten.anlegen("Lagerpalette", "Lager")
				paletten.beladen(p, charge, auf_palette, "Karton", "Lager")
		ergebnis.append({"los": los, "charge": name, "kartons": kartons})
	demo_commit()
	for e in ergebnis:
		print(f"Los {e['los']} ({e['charge']}): {e['kartons']} Karton")
	return {"lose": ergebnis}
