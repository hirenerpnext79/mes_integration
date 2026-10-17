import frappe
import requests
import json
from frappe.model.document import Document
from frappe.utils import cint, flt
from mes_integration.mes_integration.doctype.mes_configuration.mes_configuration import get_saved_mes_access_token, get_full_api_url

class StationCrossingData(Document):
	pass

def get_mes_headers():
	accesstoken = get_saved_mes_access_token()
	return {
		"Authorization": f"Bearer {accesstoken}",
		"Content-Type": "application/json",
		"Accept": "application/json"
	}

def parse_production_datetime(date_string):
	if not date_string:
		return None, None

	parts = str(date_string).replace("T", " ").split(" ")
	production_date = parts[0] if parts else None
	production_time = parts[1] if len(parts) > 1 else None
	return production_date, production_time

def build_collection_map(collection_data):
	collection_map = {}
	for item in collection_data or []:
		serial_no = item.get("seriaL_NO")
		if serial_no:
			collection_map[str(serial_no).strip()] = item
	return collection_map

def parse_station_crossing_item(item, collection_item=None):
	production_date, production_time = parse_production_datetime(
		item.get("creatioN_DATE")
	)

	row = {
		"work_order": item.get("wO_NO"),
		"serial_no": item.get("seriaL_NO"),
		"production_date_creation_date": production_date,
		"production_time_creation_date": production_time,
		"process_worker_name": item.get("workeR_NAME"),
		"qc_status_grade": item.get("grade"),
		"qc_remark_remark": item.get("remark"),
		"cell_location_errorposition": item.get("errorPosition"),
		"module_defect_code_errorcode": item.get("errorCode")
	}

	if collection_item:
		row.update({
			"pmax": flt(collection_item.get("pmax")),
			"isc": flt(collection_item.get("isc")),
			"voc": flt(collection_item.get("voc")),
			"ipm": flt(collection_item.get("ipm")),
			"vpm": flt(collection_item.get("vpm")),
			"ff": flt(collection_item.get("ff")),
			"eff": flt(collection_item.get("eff")),
			"watt_pic": collection_item.get("powerLevel"),
			"current": collection_item.get("currentLevel")
		})

	return row

def prepare_station_crossing_rows(mes_data, collection_map):
	prepared_rows = []
	for item in mes_data or []:
		serial_no = item.get("seriaL_NO")
		clean_sn = str(serial_no).strip() if serial_no else ""
		collection_item = collection_map.get(clean_sn) if clean_sn else None
		prepared_rows.append(parse_station_crossing_item(item, collection_item))
	return prepared_rows

@frappe.whitelist()
def fetch_and_store_mes_station_crossing_data(run_via_cron=False):
	is_cron = cint(run_via_cron)

	try:
		settings = frappe.get_single("MES Configuration")
		payload = {
			"LineId": settings.line_id or "L1",
			"SiteId": settings.site_id or "31"
		}

		endpoint = settings.station_crossing_data or "/api/UploadERP/GetMESStationCrossingData"
		api_url = get_full_api_url(endpoint)
		res = requests.post(api_url, headers=get_mes_headers(), json=payload, verify=False, timeout=30)

		if res.status_code != 200:
			frappe.log_error(title="Solar MES Fetch Station Crossing Error", message=res.text)
			if is_cron:
				return
			frappe.throw(f"Failed to fetch Station Crossing Data: {res.status_code} {res.text}")

		response = res.json() or {}
		result_data = response.get("result") or response
		mes_data = result_data.get("mesStationCrossingData")
		collection_data = result_data.get("collectionData")

		if not mes_data:
			msg = result_data.get("msg") or result_data.get("message") or "MES does not have any transit information"
			if is_cron:
				frappe.log_error(title="MES Station Crossing No Data (Cron)", message=json.dumps(response, indent=4))
			else:
				frappe.msgprint(msg, title="Station Crossing Data", indicator="orange")
			return {"status": "no_data", "message": msg}

		collection_map = build_collection_map(collection_data)
		crossing_rows = prepare_station_crossing_rows(mes_data, collection_map)

		new_doc = frappe.get_doc({
			"doctype": "Station Crossing Data",
			"response": json.dumps(result_data, indent=4),
			"total_serial_no_count": len(crossing_rows),
			"work_order_and_serial_no": crossing_rows
		})
		new_doc.insert(ignore_permissions=True)
		frappe.db.commit()

		if not is_cron:
			frappe.msgprint("Station Crossing Data fetched successfully", indicator="green")

		return {"status": "success", "message": "Station Crossing Data fetched successfully"}
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(title="Solar MES Fetch Station Crossing Exception", message=str(e))
		if is_cron:
			return
		frappe.throw(f"Station Crossing Data Fetch Failed: {e}")

@frappe.whitelist()
def update_station_crossing_status_data(work_order_number):
	if not work_order_number:
		frappe.throw("Work Order Number is required")

	try:
		settings = frappe.get_single("MES Configuration")
		endpoint = settings.station_crossing_status_update or "/api/UploadERP/UPdateMESStatusData"
		api_url = get_full_api_url(endpoint)

		res = requests.post(
			api_url,
			headers=get_mes_headers(),
			json={"WO_NO": work_order_number},
			verify=False,
			timeout=30
		)

		if res.status_code != 200:
			frappe.log_error(title="Solar MES Update Station Crossing Status Error", message=res.text)
			frappe.throw(f"Failed to update status: {res.status_code} {res.text}")

		data = res.json()
		result = data.get("result") or {}
		msg = result.get("message") or data.get("message")
		is_success = result.get("success") if result.get("success") is not None else data.get("success", True)

		if msg:
			frappe.msgprint(msg, indicator="green" if is_success else "red")

		return data
	except frappe.ValidationError:
		raise
	except Exception as e:
		frappe.log_error(title="Solar MES Update Station Crossing Status Exception", message=str(e))
		frappe.throw(f"Update Status Failed: {e}")

def cron_fetch_and_store_mes_station_crossing_data():
	fetch_and_store_mes_station_crossing_data(run_via_cron=True)
