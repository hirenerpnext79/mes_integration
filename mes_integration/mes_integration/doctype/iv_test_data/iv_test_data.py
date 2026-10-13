import frappe
import requests
import json
from frappe.model.document import Document
from frappe.utils import flt
from mes_integration.mes_integration.doctype.mes_configuration.mes_configuration import get_saved_mes_access_token, get_full_api_url

class IVTestData(Document):
	pass

def get_mes_headers():
	accesstoken = get_saved_mes_access_token()
	return {
		"Authorization": f"Bearer {accesstoken}",
		"Content-Type": "application/json",
		"Accept": "application/json"
	}

def update_station_crossing_iv_data(iv_items):
	if not iv_items:
		return 0

	iv_map = {item.get("seriaL_NO"): item for item in iv_items if item.get("seriaL_NO")}
	if not iv_map:
		return 0

	child_rows = frappe.get_all(
		"MES Work Order and Serial Data",
		filters={
			"parenttype": "Station Crossing Data",
			"serial_no": ["in", list(iv_map.keys())],
			"iv_data_sync": ["!=", 1]
		},
		fields=["name", "parent", "serial_no"]
	)
	if not child_rows:
		return 0

	doc_updates = {}
	parent_names = set()
	for row in child_rows:
		item = iv_map.get(row.serial_no)
		if item:
			doc_updates[row.name] = {
				"pmax": flt(item.get("pmax")),
				"isc": flt(item.get("isc")),
				"voc": flt(item.get("voc")),
				"ipm": flt(item.get("ipm")),
				"vpm": flt(item.get("vpm")),
				"ff": flt(item.get("ff")),
				"eff": flt(item.get("eff")),
				"watt_pic": item.get("powerLevel"),
				"current": item.get("currentLevel"),
				"iv_data_sync": 1
			}
			if row.parent:
				parent_names.add(row.parent)

	frappe.db.bulk_update("MES Work Order and Serial Data", doc_updates, update_modified=False)

	parent_counts = frappe.get_all(
		"MES Work Order and Serial Data",
		filters={"parent": ["in", list(parent_names)], "parenttype": "Station Crossing Data", "iv_data_sync": 1},
		group_by="parent",
		fields=["parent", "count(name) as count"]
	)
	parent_updates = {p.parent: {"update_iv_data_count": p.count} for p in parent_counts}
	frappe.db.bulk_update("Station Crossing Data", parent_updates, update_modified=False)

	return len(child_rows)

@frappe.whitelist()
def fetch_and_store_iv_test_data():
	headers = get_mes_headers()
	settings = frappe.get_single("MES Configuration")

	try:
		endpoint = settings.iv_data or "/api/UploadERP/GetIVTestData"
		api_url = get_full_api_url(endpoint)
		res = requests.post(api_url, headers=headers, json={}, verify=False, timeout=30)

		if res.status_code != 200:
			frappe.log_error(title="Solar MES Fetch IV Test Data Error", message=res.text)
			frappe.throw("Failed to fetch IV Test Data: " + str(res.status_code) + " " + res.text)

		result = res.json().get("result") or {}
		iv_items = result.get("collectionData")
		if not iv_items:
			msg = result.get("msg") or "MES does not have any transit information"
			frappe.msgprint(msg, title="IV Test Data", indicator="orange")
			return {"status": "no_data", "message": msg}

		frappe.get_doc({
			"doctype": "IV Test Data",
			"response": json.dumps(result, indent=4)
		}).insert(ignore_permissions=True)

		updated_count = update_station_crossing_iv_data(iv_items)
		frappe.db.commit()

		frappe.msgprint(f"IV Test Data fetched successfully. Updated {updated_count} serial number(s) in Station Crossing Data.", indicator="green")
		return {"status": "success", "message": "IV Test Data fetched successfully", "updated_count": updated_count}
	except Exception as e:
		frappe.log_error(title="Solar MES Fetch IV Test Data Exception", message=str(e))
		frappe.throw("IV Data Fetch Failed. Check Error Log: " + str(e))

@frappe.whitelist()
def update_iv_status_data(work_order_number):
	headers = get_mes_headers()
	settings = frappe.get_single("MES Configuration")

	try:
		endpoint = settings.iv_status_update or "/api/UploadERP/UpdateIvStatusData"
		api_url = get_full_api_url(endpoint)

		payload = {
			"WO_NO": work_order_number
		}

		res = requests.post(api_url, headers=headers, json=payload, verify=False, timeout=30)

		if res.status_code == 200:
			response_json = res.json()
			result_data = response_json.get("result") or {}
			msg = result_data.get("message") or response_json.get("message")

			is_success = result_data.get("success")
			if is_success is None:
				is_success = response_json.get("success")

			if is_success is None:
				is_success = (result_data.get("code") == 200) or (response_json.get("code") == 200)

			if msg:
				if is_success:
					frappe.msgprint(msg, title="Success", indicator="green")
				else:
					frappe.msgprint(msg, title="Error", indicator="red")

			return response_json
		else:
			frappe.log_error(title="Solar MES Update IV Status Error", message=res.text)
			frappe.throw("Failed to update status: " + str(res.status_code) + " " + res.text)
	except Exception as e:
		frappe.log_error(title="Solar MES Update IV Status Exception", message=str(e))
		frappe.throw("Update Status Failed. Check Error Log: " + str(e))
