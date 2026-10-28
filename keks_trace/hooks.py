app_name = "keks_trace"
app_title = "Keks Trace"
app_publisher = "Heinrich Schulze Ladencafe GmbH"
app_description = "Chargenrückverfolgung mit Rework für die Keksproduktion"
app_email = ""
app_license = "proprietary"

# keks_trace baut auf ERPNext auf (Chargen, Lager, Buchungen).
required_apps = ["erpnext"]

# Zusatzfelder an Artikel und Charge werden per Code angelegt,
# damit jede Instanz identisch ist (nichts in der Oberfläche zusammenklicken).
after_install = "keks_trace.install.after_install"
after_migrate = "keks_trace.install.after_migrate"

doc_events = {
	"Stock Entry": {
		# Läuft VOR der ERPNext-Prüfung, damit Bediener klare deutsche Meldungen sehen.
		"before_validate": "keks_trace.rework.pruefe_stock_entry",
		# Genealogie-Kanten und Ursprungs-/Verfallsdaten der erzeugten Chargen.
		"on_submit": "keks_trace.genealogie.on_submit",
		"on_cancel": "keks_trace.genealogie.on_cancel",
	}
}
