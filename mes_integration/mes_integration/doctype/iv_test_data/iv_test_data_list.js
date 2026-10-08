frappe.listview_settings['IV Test Data'] = {
    onload: function(listview) {
        listview.page.add_inner_button(__('Fetch Latest Data'), function() {
            frappe.call({
                method: "mes_integration.mes_integration.doctype.iv_test_data.iv_test_data.fetch_and_store_iv_test_data",
				freeze: true,
				freeze_message: __('Fetching Data from MES...'),
                callback: function(r) {
                    if (!r.exc) {
                        frappe.msgprint(__('Successfully fetched latest IV Test Data.'));
                        listview.refresh();
                    }
                }
            });
        });

        listview.page.add_inner_button(__('Update Status'), function() {
            frappe.prompt([
                {
                    label: 'Work Order Number',
                    fieldname: 'work_order_number',
                    fieldtype: 'Data',
                    reqd: 1
                }
            ],
            function(values) {
                frappe.call({
                    method: "mes_integration.mes_integration.doctype.iv_test_data.iv_test_data.update_iv_status_data",
                    type: "POST",
                    args: {
                        work_order_number: values.work_order_number
                    },
                    freeze: true,
                    freeze_message: __('Updating Status...'),
                    callback: function(r) {
                        listview.refresh();
                    }
                });
            },
            __('Update Status'),
            __('Submit'));
        });
    }
};
