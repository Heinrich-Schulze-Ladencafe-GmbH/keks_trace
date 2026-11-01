#!/usr/bin/env bash
# Testserver für keks_trace auf einem frischen Debian 13 (trixie) einrichten – in einem Lauf.
#
#   sudo bash testserver-einrichten.sh            # einrichten (mit Testfirma und Demo-Daten)
#   sudo bash testserver-einrichten.sh --update   # neuesten Stand von keks_trace holen und einspielen
#
# Optionen: --ohne-demo  --site NAME (Standard: keks-test)  --branch NAME (Standard: main)
# Ist das Repository privat, fragt das Skript nach einem GitHub-Token (nur Lesezugriff) oder nimmt
# es aus der Umgebung: KT_TOKEN=... sudo -E bash testserver-einrichten.sh
#
# Wiederholbar: bricht ein Lauf ab, einfach nochmal starten; Erledigtes wird übersprungen.
# Zugangsdaten (Administrator, Datenbank) stehen danach in /root/keks-zugang.txt, nirgends sonst.

set -Eeuo pipefail

REPO="https://github.com/Heinrich-Schulze-Ladencafe-GmbH/keks_trace"
BRANCH="main"
SITE="keks-test"
DEMO=1
UPDATE=0
FRAPPE_BRANCH="version-16"
PY_VERSION="3.14"
NODE_MAJOR="24"
BENCH_USER="frappe"
BENCH_HOME="/home/${BENCH_USER}"
BENCH="${BENCH_HOME}/frappe-bench"
ZUGANG="/root/keks-zugang.txt"
FIRMA="Keks Test GmbH"
KUERZEL="KTG"

while [ $# -gt 0 ]; do
	case "$1" in
		--update) UPDATE=1 ;;
		--ohne-demo) DEMO=0 ;;
		--site) SITE="$2"; shift ;;
		--branch) BRANCH="$2"; shift ;;
		-h|--help) sed -n '2,13p' "$0"; exit 0 ;;
		*) echo "Unbekannte Option: $1" >&2; exit 2 ;;
	esac
	shift
done

# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------
schritt() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
hinweis() { printf '\033[0;33m    %s\033[0m\n' "$*"; }
fehler()  { printf '\n\033[1;31mFEHLER: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'printf "\n\033[1;31mAbgebrochen in Zeile %s: %s\033[0m\nEinfach nochmal starten; Erledigtes wird übersprungen.\n" "$LINENO" "$BASH_COMMAND" >&2' ERR

# Befehl als Benutzer frappe im Bench-Verzeichnis (mit Node und uv im Pfad)
als_frappe() {
	sudo -u "$BENCH_USER" -H bash -c "export PATH=\"/opt/node${NODE_MAJOR}/bin:${BENCH_HOME}/.local/bin:\$PATH\"; cd \"${BENCH}\" 2>/dev/null || cd ~; $*"
}

# Die Redis-Dienste der Bench (config/redis_*.conf): Seite anlegen, Einrichtung und Demos brauchen
# sie; im Dauerbetrieb startet sie supervisor. Vorher selbst starten, vor dem Dauerbetrieb beenden.
redis_bench() {  # redis_bench start|stop
	local conf port
	for conf in "$BENCH"/config/redis_*.conf; do
		[ -f "$conf" ] || continue
		port="$(awk '$1 == "port" {print $2}' "$conf")"
		[ -n "$port" ] || continue
		if [ "$1" = start ]; then
			als_frappe "redis-cli -p ${port} ping >/dev/null 2>&1 || redis-server ${conf} --daemonize yes >/dev/null"
		else
			als_frappe "redis-cli -p ${port} shutdown nosave >/dev/null 2>&1 || true"
		fi
	done
}

passwort() { tr -dc 'A-Za-z0-9' </dev/urandom | head -c 20; }

zugang_lesen() { [ -f "$ZUGANG" ] && grep -E "^$1=" "$ZUGANG" | cut -d= -f2- || true; }

# ---------------------------------------------------------------------------
# Prüfen
# ---------------------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || fehler "Bitte als root starten: sudo bash $0"
. /etc/os-release
if [ "${VERSION_CODENAME:-}" != "trixie" ]; then
	hinweis "Gedacht für Debian 13 (trixie), gefunden: ${PRETTY_NAME:-unbekannt}. Weiter in 10 Sekunden (Strg+C bricht ab)."
	sleep 10
fi

# ---------------------------------------------------------------------------
# Update: nur keks_trace holen, migrieren, neu starten
# ---------------------------------------------------------------------------
if [ "$UPDATE" -eq 1 ]; then
	[ -d "$BENCH/apps/keks_trace" ] || fehler "Noch nicht eingerichtet. Erst ohne --update starten."
	schritt "keks_trace aktualisieren"
	if ! als_frappe "git -C apps/keks_trace pull --ff-only" ; then
		read -r -s -p "GitHub-Token (Lesezugriff): " KT_TOKEN; echo
		als_frappe "git -C apps/keks_trace pull --ff-only https://x-access-token:${KT_TOKEN}@${REPO#https://} ${BRANCH}"
	fi
	schritt "Datenbank anpassen und Oberfläche bauen"
	als_frappe "bench --site ${SITE} migrate && bench build --app keks_trace && bench --site ${SITE} clear-cache"
	supervisorctl restart all >/dev/null
	schritt "Fertig: $(als_frappe 'git -C apps/keks_trace log --oneline -1')"
	exit 0
fi

# ---------------------------------------------------------------------------
# 1. Systempakete
# ---------------------------------------------------------------------------
schritt "Systempakete installieren"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q sudo git curl ca-certificates xz-utils build-essential pkg-config \
	mariadb-server mariadb-client libmariadb-dev nginx supervisor cron \
	chromium fonts-dejavu-core fonts-liberation2 locales >/dev/null
# Redis: Debian 13 hat redis-server; falls nicht, Valkey mit Redis-Namen
if ! apt-get install -y -q redis-server >/dev/null 2>&1; then
	apt-get install -y -q valkey-server valkey-redis-compat >/dev/null
fi
command -v redis-server >/dev/null || fehler "redis-server nicht gefunden."
# wkhtmltopdf gibt es in Debian 13 nicht mehr; PDFs macht Frappe 16 mit Chromium (unten eingestellt)
sed -i 's/^# *de_DE.UTF-8/de_DE.UTF-8/' /etc/locale.gen && locale-gen >/dev/null
systemctl enable --now mariadb redis-server 2>/dev/null || systemctl enable --now mariadb

# ---------------------------------------------------------------------------
# 2. Node (offizielles Paket) und Benutzer frappe mit uv und Python
# ---------------------------------------------------------------------------
schritt "Node ${NODE_MAJOR} installieren"
if [ ! -x "/opt/node${NODE_MAJOR}/bin/node" ]; then
	arch="$(dpkg --print-architecture)"; case "$arch" in amd64) arch=x64 ;; arm64) arch=arm64 ;; *) fehler "Architektur $arch nicht unterstützt" ;; esac
	basis="https://nodejs.org/dist/latest-v${NODE_MAJOR}.x"
	tmp="$(mktemp -d)"
	curl -fsSL "$basis/SHASUMS256.txt" -o "$tmp/SHASUMS256.txt"
	datei="$(grep -oE "node-v[0-9.]+-linux-${arch}\.tar\.xz" "$tmp/SHASUMS256.txt" | head -1)"
	curl -fsSL "$basis/$datei" -o "$tmp/$datei"
	(cd "$tmp" && grep " $datei\$" SHASUMS256.txt | sha256sum -c - >/dev/null) || fehler "Prüfsumme von $datei falsch"
	mkdir -p "/opt/node${NODE_MAJOR}" && tar -xJf "$tmp/$datei" -C "/opt/node${NODE_MAJOR}" --strip-components=1
	rm -rf "$tmp"
fi
for b in node npm npx; do ln -sf "/opt/node${NODE_MAJOR}/bin/$b" "/usr/local/bin/$b"; done
[ -x "/opt/node${NODE_MAJOR}/bin/yarn" ] || /opt/node${NODE_MAJOR}/bin/npm install -g yarn >/dev/null
ln -sf "/opt/node${NODE_MAJOR}/bin/yarn" /usr/local/bin/yarn
hinweis "node $(node --version), yarn $(yarn --version)"

schritt "Benutzer ${BENCH_USER}, uv, Python ${PY_VERSION} und bench"
id "$BENCH_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$BENCH_USER"
chmod 755 "$BENCH_HOME"   # nginx muss die Dateien unter sites/ lesen können
als_frappe "command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null"
als_frappe "uv python install ${PY_VERSION} >/dev/null"
als_frappe "command -v bench >/dev/null || uv tool install --python ${PY_VERSION} frappe-bench >/dev/null"
ln -sf "${BENCH_HOME}/.local/bin/bench" /usr/local/bin/bench
hinweis "$(als_frappe 'bench --version' | tail -1) mit Python $(als_frappe "uv python find ${PY_VERSION}")"

# ---------------------------------------------------------------------------
# 3. MariaDB: utf8mb4 und Passwort für root (Frappe meldet sich per Passwort an)
# ---------------------------------------------------------------------------
schritt "MariaDB einrichten"
DB_ROOT="$(zugang_lesen DB_ROOT_PASSWORT)"
ADMIN="$(zugang_lesen ADMIN_PASSWORT)"
[ -n "$DB_ROOT" ] || DB_ROOT="$(passwort)"
[ -n "$ADMIN" ] || ADMIN="$(passwort)"
umask 077
cat > "$ZUGANG" <<EOF
# keks_trace Testserver – Zugangsdaten (nur root lesbar)
SITE=${SITE}
ADMIN_BENUTZER=Administrator
ADMIN_PASSWORT=${ADMIN}
DB_ROOT_PASSWORT=${DB_ROOT}
EOF
umask 022
cat > /etc/mysql/mariadb.conf.d/90-frappe.cnf <<'EOF'
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

[mysql]
default-character-set = utf8mb4
EOF
systemctl restart mariadb
# root: Passwort und weiterhin Anmeldung über den Unix-Socket (für Debians eigene Wartung)
if mysql -uroot -e "select 1" >/dev/null 2>&1; then
	mysql -uroot -e "ALTER USER 'root'@'localhost' IDENTIFIED VIA unix_socket OR mysql_native_password USING PASSWORD('${DB_ROOT}'); FLUSH PRIVILEGES;"
fi
mysql -uroot -p"${DB_ROOT}" -h 127.0.0.1 -e "select 1" >/dev/null || fehler "Anmeldung an MariaDB mit Passwort klappt nicht."

# ---------------------------------------------------------------------------
# 4. Bench mit Frappe, ERPNext, DATEV, E-Rechnung und keks_trace
# ---------------------------------------------------------------------------
schritt "Frappe ${FRAPPE_BRANCH} (bench init, dauert einige Minuten)"
if [ ! -d "$BENCH/apps/frappe" ]; then
	sudo -u "$BENCH_USER" -H bash -c "export PATH=\"/opt/node${NODE_MAJOR}/bin:${BENCH_HOME}/.local/bin:\$PATH\"; cd ~ && \
		bench init --frappe-branch ${FRAPPE_BRANCH} --python \"\$(uv python find ${PY_VERSION})\" frappe-bench" \
		|| fehler "bench init fehlgeschlagen"
fi

app_holen() {  # app_holen NAME URL BRANCH
	[ -d "$BENCH/apps/$1" ] && { hinweis "$1 ist schon da"; return; }
	schritt "App $1 holen"
	als_frappe "bench get-app --branch $3 $2"
}
app_holen erpnext https://github.com/frappe/erpnext "$FRAPPE_BRANCH"
app_holen eu_einvoice https://github.com/alyf-de/eu_einvoice "$FRAPPE_BRANCH"
app_holen erpnext_datev https://github.com/alyf-de/erpnext_datev "$FRAPPE_BRANCH"

if [ ! -d "$BENCH/apps/keks_trace" ]; then
	schritt "keks_trace holen"
	URL="$REPO"
	if ! git ls-remote "$REPO" >/dev/null 2>&1; then
		hinweis "Das Repository ist nicht öffentlich erreichbar."
		[ -n "${KT_TOKEN:-}" ] || { read -r -s -p "    GitHub-Token (nur Lesezugriff auf keks_trace): " KT_TOKEN; echo; }
		URL="https://x-access-token:${KT_TOKEN}@${REPO#https://}"
	fi
	als_frappe "bench get-app --branch ${BRANCH} ${URL}"
	# Token nicht im Repository stehen lassen
	als_frappe "git -C apps/keks_trace remote set-url upstream ${REPO} 2>/dev/null; git -C apps/keks_trace remote set-url origin ${REPO} 2>/dev/null; true"
fi

# ---------------------------------------------------------------------------
# 5. Seite anlegen, Apps installieren, Einrichtung auf Deutsch
# ---------------------------------------------------------------------------
redis_bench start
schritt "Seite ${SITE} anlegen"
if [ ! -d "$BENCH/sites/$SITE" ]; then
	als_frappe "bench new-site ${SITE} --admin-password '${ADMIN}' --db-root-username root --db-root-password '${DB_ROOT}'"
fi
als_frappe "bench use ${SITE}"
for app in erpnext eu_einvoice erpnext_datev keks_trace; do
	if ! als_frappe "bench --site ${SITE} list-apps" | grep -qw "$app"; then
		schritt "App ${app} installieren"
		als_frappe "bench --site ${SITE} install-app ${app}"
	fi
done
# PDFs mit Chromium aus Debian statt wkhtmltopdf
als_frappe "bench config set-common-config -c chromium_path /usr/bin/chromium"

schritt "Einrichtungsassistent (Deutsch, ${FIRMA}, Geschäftsjahr $(date +%Y))"
eingerichtet() { als_frappe "bench --site ${SITE} execute frappe.is_setup_complete" | grep -qi true; }
if ! eingerichtet; then
	JAHR="$(date +%Y)"
	als_frappe "bench --site ${SITE} execute frappe.desk.page.setup_wizard.setup_wizard.setup_complete --kwargs \"{'args': {'language': 'Deutsch', 'country': 'Germany', 'timezone': 'Europe/Berlin', 'currency': 'EUR', 'full_name': 'Test Admin', 'email': 'admin@example.com', 'password': '${ADMIN}', 'company_name': '${FIRMA}', 'company_abbr': '${KUERZEL}', 'chart_of_accounts': 'Standard', 'fy_start_date': '${JAHR}-01-01', 'fy_end_date': '${JAHR}-12-31'}}\""
	eingerichtet || fehler "Einrichtungsassistent nicht abgeschlossen."
fi
als_frappe "bench --site ${SITE} execute frappe.db.set_single_value --args \"['Print Settings', 'pdf_generator', 'chrome']\"" >/dev/null \
	|| hinweis "PDF-Erzeuger bitte von Hand in den Druckeinstellungen auf Chrome stellen."

# ---------------------------------------------------------------------------
# 6. Demo-Daten (einmal)
# ---------------------------------------------------------------------------
MARKE="$BENCH/sites/$SITE/private/.kt_demo_fertig"
demo() {  # demo METHODE [KWARGS]
	schritt "Demo: $1"
	if [ -n "${2:-}" ]; then
		als_frappe "bench --site ${SITE} execute keks_trace.$1 --kwargs \"$2\"" | tail -1
	else
		als_frappe "bench --site ${SITE} execute keks_trace.$1" | tail -1
	fi
}
if [ "$DEMO" -eq 1 ] && [ ! -f "$MARKE" ]; then
	demo demo.run
	demo demo_linie.anlegen
	demo pilot.anlegen
	demo pilot.durchspielen
	demo demo_herzen.anlegen
	demo demo_herzen.durchlauf "{'groesse': '9', 'stueck': 100}"
	demo demo_einkauf.anlegen
	demo demo_erechnung.einrichten
	sudo -u "$BENCH_USER" touch "$MARKE"
fi

# ---------------------------------------------------------------------------
# 7. Dauerbetrieb: nginx und supervisor (startet nach Neustart von selbst)
# ---------------------------------------------------------------------------
redis_bench stop   # supervisor startet sie gleich selbst
schritt "Produktivbetrieb einrichten (nginx, supervisor)"
rm -f /etc/nginx/sites-enabled/default   # sonst antwortet nginx statt Frappe auf http://<IP>
cd "$BENCH"
bench setup production "$BENCH_USER" --yes
systemctl enable --now supervisor nginx >/dev/null 2>&1 || true
supervisorctl reread >/dev/null && supervisorctl update >/dev/null && supervisorctl restart all >/dev/null
nginx -t >/dev/null 2>&1 && systemctl reload nginx

# ---------------------------------------------------------------------------
# Fertig
# ---------------------------------------------------------------------------
IP="$(hostname -I | awk '{print $1}')"
sleep 3
if curl -fsS -o /dev/null "http://127.0.0.1/api/method/ping"; then STATUS="läuft"; else STATUS="antwortet noch nicht – in einer Minute nochmal probieren"; fi
cat <<EOF

=========================================================================
  Fertig. ERPNext ${STATUS}.

  Im Browser:   http://${IP}/app          (Terminal: http://${IP}/terminal)
  Anmeldung:    Administrator / Passwort in ${ZUGANG}

  Drucker:      Etikettendrucker anlegen (IP, Port 9100, Auflösung, Rolle),
                Testdruck, dann an der Terminal Station zuordnen.
  Update:       sudo bash $0 --update
=========================================================================
EOF
