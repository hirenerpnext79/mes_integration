// Copyright (c) 2026, Mes Integration and contributors
// For license information, please see license.txt

frappe.ui.form.on("MES Configuration", {
	refresh(frm) {
		frm.add_custom_button(__('Generate Token'), function() {
			frappe.call({
				method: "mes_integration.mes_integration.doctype.mes_configuration.mes_configuration.get_mes_access_token",
				freeze: true,
				freeze_message: __("Generating Token..."),
				callback: function(r) {
					if (!r.exc) {
						frappe.msgprint(__('Token Generated Successfully'));
						frm.reload_doc();
					}
				}
			});
		});
	},
});
