import frappe
from mes_integration.mes_integration.doctype.mes_watt_pic_master.mes_watt_pic_master import (
    populate_watt_pic_master
)


def execute():
    try:
        frappe.reload_doc("mes_integration", "doctype", "mes_watt_pic_master")
        result = populate_watt_pic_master(start_watt=500.0, end_watt=700.0, step=5.0)
        if not result.get("success"):
            frappe.log_error(result.get("message"), "Patch populate_mes_watt_pic_master")
    except Exception as e:
        frappe.log_error(f"Error executing patch populate_mes_watt_pic_master: {str(e)}", "Patch populate_mes_watt_pic_master")
        raise
