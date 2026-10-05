frappe.listview_settings['Station Crossing Data'] = {
    onload: function(listview) {
        listview.page.add_inner_button(__('Fetch Latest Data'), function() {
            frappe.call({
                method: "mes_integration.mes_integration.doctype.station_crossing_data.station_crossing_data.fetch_and_store_mes_station_crossing_data",
				freeze: true,
				freeze_message: __('Fetching Data from MES...'),
                callback: function(r) {
                    if (!r.exc) {
                        frappe.msgprint(__('Successfully fetched latest Station Crossing Data.'));
                        listview.refresh();
                    }
                }
            });
        });
    }
};
