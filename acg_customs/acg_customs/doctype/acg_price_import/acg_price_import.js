// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

frappe.ui.form.on("ACG Price Import", {
	refresh(frm) {
		acg_render_price_preflight(frm);
		if (frm.is_new()) return;

		const status = frm.doc.status;

		if (["Uploaded", "Preflight Failed", "Preflight Passed"].includes(status)) {
			frm.add_custom_button(__("Ejecutar Preflight"), () => {
				frappe.call({
					method: "acg_customs.acg_customs.price_import.service.run_preflight",
					args: { price_import: frm.doc.name },
					freeze: true,
					freeze_message: __("Ejecutando preflight..."),
					callback: (r) => {
						const res = r.message || {};
						frappe.show_alert({
							message: __("Preflight: {0}", [res.result || "?"]),
							indicator: res.result === "PASS" ? "green" : "red",
						});
						frm.reload_doc();
					},
				});
			});
		}

		if (status === "Preflight Passed") {
			frm.add_custom_button(__("Aplicar Precios"), () => {
				frappe.confirm(__("¿Aplicar los precios a la Price List?"), () => {
					frappe.call({
						method: "acg_customs.acg_customs.price_import.service.apply_prices",
						args: { price_import: frm.doc.name },
						freeze: true,
						freeze_message: __("Aplicando precios..."),
						callback: (r) => {
							const res = r.message || {};
							frappe.show_alert({
								message: __("Precios: {0} nuevos, {1} cambiados", [
									res.new || 0,
									res.changed || 0,
								]),
								indicator: "green",
							});
							frm.reload_doc();
						},
					});
				});
			}).addClass("btn-primary");
		}
	},
});

function acg_render_price_preflight(frm) {
	const field = frm.get_field("preflight_report_html");
	if (!field || !field.$wrapper) return;
	const $w = field.$wrapper;

	if (!frm.doc.preflight_summary) {
		$w.html(`<div class="text-muted">${__("Sin preflight ejecutado todavía.")}</div>`);
		return;
	}

	let s;
	try {
		s = JSON.parse(frm.doc.preflight_summary);
	} catch (e) {
		$w.html(`<div class="text-muted">${__("Resumen no legible.")}</div>`);
		return;
	}

	const pass = s.result === "PASS";
	const badge = `<span class="indicator-pill ${
		pass ? "green" : "red"
	}">${frappe.utils.escape_html(s.result || "?")}</span>`;

	const rows = [
		[__("Productos (filas)"), s.total_rows],
		[__("Resueltos"), s.resolved],
		[__("No resueltos"), s.unresolved],
		[__("Nuevos"), s.new],
		[__("Cambiados"), s.changed],
		[__("Sin cambio"), s.unchanged],
	];
	const tr = rows
		.map(
			([k, v]) =>
				`<tr><td style="padding:2px 14px 2px 0;color:#6c7680">${k}</td>` +
				`<td>${
					v === undefined || v === null ? "—" : frappe.utils.escape_html(String(v))
				}</td></tr>`
		)
		.join("");

	const warn = (s.warnings || []).map((w) => `<li>${frappe.utils.escape_html(w)}</li>`).join("");
	const errs = (s.errors || []).map((e) => `<li>${frappe.utils.escape_html(e)}</li>`).join("");

	$w.html(`
		<div style="margin-bottom:8px">${__("Resultado")}: ${badge}</div>
		<table style="font-size:12px">${tr}</table>
		${warn ? `<div style="margin-top:8px"><b>${__("Warnings")}</b><ul>${warn}</ul></div>` : ""}
		${
			errs
				? `<div style="margin-top:8px;color:#b00"><b>${__(
						"Errores"
				  )}</b><ul>${errs}</ul></div>`
				: ""
		}
	`);
}
