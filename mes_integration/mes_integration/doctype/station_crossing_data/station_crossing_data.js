frappe.ui.form.on('MES Work Order and Serial Data', {
    upload: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        
        frappe.call({
            method: "mes_integration.mes_integration.doctype.station_crossing_data.station_crossing_data.upload_single_child_to_live",
            args: {
                parent_name: frm.doc.name,
                child_name: row.name
            },
            freeze: true,
            freeze_message: __('Uploading to Live ERPNext...'),
            callback: function(r) {
                if (!r.exc) {
                    if (r.message && r.message.status === "success") {
                        frappe.msgprint({
                            title: __('Success'),
                            indicator: 'green',
                            message: __('Successfully uploaded row to live server.')
                        });
                    }
                }
            }
        });
    }
});
