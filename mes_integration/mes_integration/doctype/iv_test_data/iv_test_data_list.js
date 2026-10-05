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
    }
};
