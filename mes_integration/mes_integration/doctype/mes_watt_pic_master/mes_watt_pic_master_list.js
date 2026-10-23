frappe.listview_settings["MES Watt Pic Master"] = {
    onload: function(listview) {
        listview.page.add_inner_button(__("Auto Generate Ranges"), function() {
            frappe.prompt(
                [
                    {
                        fieldname: "start_watt",
                        fieldtype: "Float",
                        label: __("Start Watt"),
                        default: 500,
                        reqd: 1
                    },
                    {
                        fieldname: "end_watt",
                        fieldtype: "Float",
                        label: __("End Watt"),
                        default: 700,
                        reqd: 1
                    },
                    {
                        fieldname: "step",
                        fieldtype: "Float",
                        label: __("Step Points"),
                        default: 5,
                        reqd: 1
                    }
                ],
                function(values) {
                    frappe.call({
                        method: "mes_integration.mes_integration.doctype.mes_watt_pic_master.mes_watt_pic_master.populate_watt_pic_master",
                        args: {
                            start_watt: values.start_watt,
                            end_watt: values.end_watt,
                            step: values.step
                        },
                        freeze: true,
                        freeze_message: __("Generating MES Watt Pic Master ranges..."),
                        callback: function(r) {
                            if (!r.exc && r.message && r.message.success) {
                                frappe.show_alert({
                                    message: r.message.message,
                                    indicator: "green"
                                });
                                listview.refresh();
                            }
                        }
                    });
                },
                __("Generate Watt Pic Ranges"),
                __("Generate")
            );
        });
    }
};
