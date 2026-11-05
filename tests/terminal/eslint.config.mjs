// Strenge Prüfung der Terminal-Module (keks_trace/public/js/terminal): fehlende Imports, Zuweisung an
// Imports, Unbenutztes. Läuft in der CI:
//   npx eslint@10 -c tests/terminal/eslint.config.mjs --no-config-lookup keks_trace/public/js/terminal
export default [
	{
		files: ["**/*.js"],
		languageOptions: {
			ecmaVersion: 2022,
			sourceType: "module",
			globals: {
				window: "readonly", document: "readonly", navigator: "readonly", location: "readonly", history: "readonly",
				localStorage: "readonly", fetch: "readonly", URLSearchParams: "readonly", setTimeout: "readonly",
				clearTimeout: "readonly", setInterval: "readonly", MutationObserver: "readonly", Event: "readonly",
				KeyboardEvent: "readonly", crypto: "readonly", frappe: "readonly", console: "readonly", Date: "readonly",
				performance: "readonly", Image: "readonly", URL: "readonly", requestAnimationFrame: "readonly",
			},
		},
		rules: {
			"no-undef": "error",
			"no-import-assign": "error",
			"no-redeclare": "error",
			"no-unused-vars": ["error", { vars: "all", args: "none", caughtErrors: "none" }],
			"no-dupe-keys": "error",
		},
	},
];
