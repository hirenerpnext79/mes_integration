import frappe
from frappe.model.document import Document
from frappe.utils import flt


class MESWattPicMaster(Document):
    pass


def get_watt_pic_ranges(start_watt=500.0, end_watt=700.0, step=5.0):
    ranges = []
    current = flt(start_watt)
    target_end = flt(end_watt)
    step_val = flt(step)

    while current <= target_end:
        start_range = flt(current, 2)
        start_end = flt(round(current + step_val - 0.01, 2), 2)
        watt_pic = flt(current, 2)

        ranges.append({
            "start_range": start_range,
            "start_end": start_end,
            "watt_pic": watt_pic
        })
        current = round(current + step_val, 2)

    return ranges


def save_watt_pic_record(start_range, start_end, watt_pic):
    existing_name = frappe.db.get_value(
        "MES Watt Pic Master",
        {"watt_pic": watt_pic},
        "name"
    )
    if not existing_name:
        existing_name = frappe.db.get_value(
            "MES Watt Pic Master",
            {"start_range": start_range},
            "name"
        )

    if existing_name:
        doc = frappe.get_doc("MES Watt Pic Master", existing_name)
        doc.start_range = start_range
        doc.start_end = start_end
        doc.watt_pic = watt_pic
        doc.save(ignore_permissions=True)
        return "updated"

    doc = frappe.get_doc({
        "doctype": "MES Watt Pic Master",
        "start_range": start_range,
        "start_end": start_end,
        "watt_pic": watt_pic
    })
    doc.insert(ignore_permissions=True)
    return "created"


@frappe.whitelist()
def populate_watt_pic_master(start_watt=500.0, end_watt=700.0, step=5.0):
    try:
        start_val = flt(start_watt)
        end_val = flt(end_watt)
        step_val = flt(step)

        if step_val <= 0:
            return {
                "success": False,
                "message": "Step value must be greater than zero"
            }

        if start_val > end_val:
            return {
                "success": False,
                "message": "Start watt cannot be greater than end watt"
            }

        ranges = get_watt_pic_ranges(start_val, end_val, step_val)
        created_count = 0
        updated_count = 0

        for item in ranges:
            action = save_watt_pic_record(
                item["start_range"],
                item["start_end"],
                item["watt_pic"]
            )
            if action == "created":
                created_count += 1
            else:
                updated_count += 1

        frappe.db.commit()

        return {
            "success": True,
            "message": f"Successfully processed {len(ranges)} ranges ({created_count} created, {updated_count} updated)",
            "data": {
                "total": len(ranges),
                "created": created_count,
                "updated": updated_count
            }
        }
    except Exception as e:
        frappe.log_error(f"Error populating MES Watt Pic Master: {str(e)}", "MES Watt Pic Master")
        return {
            "success": False,
            "message": str(e)
        }
