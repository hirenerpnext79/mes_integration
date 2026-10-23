import json
import frappe
import requests
from frappe.model.document import Document
from frappe.utils import flt
from mes_integration.mes_integration.doctype.mes_configuration.mes_configuration import (
	get_full_api_url,
	get_saved_mes_access_token
)
from mes_integration.mes_integration.doctype.station_crossing_data.station_crossing_data import (
	build_collection_map,
	get_watt_pic_masters,
	match_watt_pic
)

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

	iv_map, iv_counts = build_collection_map(iv_items)
	if not iv_map:
		return 0

	child_rows = frappe.get_all(
		"MES Work Order and Serial Data",
		filters={
			"parenttype": "Station Crossing Data",
			"serial_no": ["in", list(iv_map.keys())]
		},
		fields=["name", "parent", "serial_no", "is_multiple", "error"]
	)
	if not child_rows:
		return 0

	watt_pic_masters = get_watt_pic_masters()
	doc_updates = {}
	parent_names = set()

	for row in child_rows:
		clean_sn = str(row.serial_no).strip()
		item = iv_map.get(clean_sn)
		if item:
			pmax = flt(item.get("pmax"))
			matched_watt_pic = match_watt_pic(pmax, watt_pic_masters)
			watt_pic = matched_watt_pic if matched_watt_pic is not None else item.get("powerLevel")

			row_error = ""
			if matched_watt_pic is None and pmax > 0:
				row_error = f"Watt Pic range not found for Pmax {pmax} in MES Watt Pic Master"
			elif not pmax:
				row_error = "Pmax missing or invalid in IV data"

			is_multiple = 1 if (iv_counts.get(clean_sn, 0) > 1 or row.is_multiple) else 0

			doc_updates[row.name] = {
				"pmax": pmax,
				"isc": flt(item.get("isc")),
				"voc": flt(item.get("voc")),
				"ipm": flt(item.get("ipm")),
				"vpm": flt(item.get("vpm")),
				"ff": flt(item.get("ff")),
				"eff": flt(item.get("eff")),
				"watt_pic": watt_pic,
				"current": item.get("currentLevel"),
				"is_multiple": is_multiple,
				"error": row_error,
				"iv_data_sync": 1,
				"collection_date": item.get("collectioN_DATE")
			}
			if row.parent:
				parent_names.add(row.parent)

	frappe.db.bulk_update("MES Work Order and Serial Data", doc_updates, update_modified=False)
	return len(child_rows)

@frappe.whitelist()
def fetch_and_store_iv_test_data(run_via_cron=False):
	headers = get_mes_headers()
	settings = frappe.get_single("MES Configuration")

	try:
		endpoint = settings.iv_data or "/api/UploadERP/GetIVTestData"
		api_url = get_full_api_url(endpoint)
		res = requests.post(api_url, headers=headers, json={}, verify=False, timeout=30)

		if res.status_code != 200:
			frappe.log_error(title="Solar MES Fetch IV Test Data Error", message=res.text)
			if run_via_cron:
				return
			frappe.throw(f"Failed to fetch IV Test Data: {res.status_code} {res.text}")

		result = res.json().get("result") or {}
		iv_items = result.get("collectionData")
		if not iv_items:
			msg = result.get("msg") or "MES does not have any transit information"
			if run_via_cron:
				frappe.log_error(title="MES IV Data No Data (Cron)", message=json.dumps(result, indent=4))
			else:
				frappe.msgprint(msg, title="IV Test Data", indicator="orange")
			return {"status": "no_data", "message": msg}

		frappe.get_doc({
			"doctype": "IV Test Data",
			"response": json.dumps(result, indent=4)
		}).insert(ignore_permissions=True)

		updated_count = update_station_crossing_iv_data(iv_items)
		frappe.db.commit()

		if not run_via_cron:
			frappe.msgprint(f"IV Test Data fetched successfully. Updated {updated_count} serial number(s) in Station Crossing Data.", indicator="green")
		return {"status": "success", "message": "IV Test Data fetched successfully", "updated_count": updated_count}
	except Exception as e:
		frappe.log_error(title="Solar MES Fetch IV Test Data Exception", message=str(e))
		if run_via_cron:
			return
		frappe.throw(f"IV Data Fetch Failed: {e}")

@frappe.whitelist()
def update_iv_status_data(work_order_number):
	if not work_order_number:
		frappe.throw("Work Order Number is required")

	settings = frappe.get_single("MES Configuration")
	endpoint = settings.iv_status_update or "/api/UploadERP/UpdateIvStatusData"
	api_url = get_full_api_url(endpoint)

	try:
		res = requests.post(
			api_url,
			headers=get_mes_headers(),
			json={"WO_NO": work_order_number},
			verify=False,
			timeout=30
		)

		if res.status_code != 200:
			frappe.log_error(title="Solar MES Update IV Status Error", message=res.text)
			frappe.throw(f"Failed to update status: {res.status_code} {res.text}")

		data = res.json()
		result = data.get("result") or {}
		msg = result.get("message") or data.get("message")
		is_success = result.get("success") if result.get("success") is not None else data.get("success", True)

		if msg:
			frappe.msgprint(msg, indicator="green" if is_success else "red")

		return data
	except Exception as e:
		frappe.log_error(title="Solar MES Update IV Status Exception", message=str(e))
		frappe.throw(f"Update Status Failed: {e}")

def cron_fetch_and_store_iv_test_data():
	fetch_and_store_iv_test_data(run_via_cron=True)
