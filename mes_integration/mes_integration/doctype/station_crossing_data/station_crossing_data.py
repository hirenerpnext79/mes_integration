import frappe
import requests
import json
from frappe.model.document import Document
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

def parse_station_crossing_item(item):
	creation_date_str = item.get("creatioN_DATE", "")
	production_date = None
	production_time = None

	if creation_date_str:
		parts = creation_date_str.split("T") if "T" in creation_date_str else creation_date_str.split(" ")
		if len(parts) >= 1:
			production_date = parts[0]
		if len(parts) >= 2:
			production_time = parts[1]

	return {
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

@frappe.whitelist()
def fetch_and_store_mes_station_crossing_data(run_via_cron=False):
	settings = frappe.get_single("MES Configuration")
	headers = get_mes_headers()

	try:
		payload = {
			"LineId": settings.line_id or "L1",
			"SiteId": settings.site_id or "31"
		}

		endpoint = settings.station_crossing_data or "/api/UploadERP/GetMESStationCrossingData"
		api_url = get_full_api_url(endpoint)
		res = requests.post(api_url, headers=headers, json=payload, verify=False, timeout=30)

		if res.status_code == 200:
			response = res.json()
			raw_result = response.get("result") if isinstance(response, dict) and "result" in response else response
			result_data = frappe._dict(raw_result or {})

			mes_data = result_data.get("mesStationCrossingData")
			if not mes_data:
				msg = result_data.get("msg") or "MES does not have any transit information"
				if run_via_cron:
					frappe.log_error(title="MES Station Crossing No Data (Cron)", message=json.dumps(response, indent=4))
				else:
					frappe.msgprint(msg, title="Station Crossing Data", indicator="orange")
				return {"status": "no_data", "message": msg}

			new_doc = frappe.new_doc("Station Crossing Data")
			new_doc.response = json.dumps(result_data, indent=4)

			for item in mes_data:
				new_doc.append("work_order_and_serial_no", parse_station_crossing_item(item))

			new_doc.total_serial_no_count = len(new_doc.work_order_and_serial_no)
			new_doc.insert(ignore_permissions=True)

			frappe.db.commit()
			if not run_via_cron:
				frappe.msgprint("Station Crossing Data fetched successfully", indicator="green")

			return {"status": "success", "message": "Station Crossing Data fetched successfully"}
		else:
			frappe.log_error(title="Solar MES Fetch Station Crossing Error", message=res.text)
			if run_via_cron:
				return
			else:
				frappe.throw("Failed to fetch Station Crossing Data: " + str(res.status_code) + " " + res.text)
	except Exception as e:
		frappe.log_error(title="Solar MES Fetch Station Crossing Exception", message=str(e))
		if run_via_cron:
			return
		else:
			frappe.throw("Station Crossing Data Fetch Failed. Check Error Log: " + str(e))

@frappe.whitelist()
def update_station_crossing_status_data(work_order_number):
	headers = get_mes_headers()
	settings = frappe.get_single("MES Configuration")

	try:
		endpoint = settings.station_crossing_status_update or "/api/UploadERP/UPdateMESStatusData"
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
			frappe.log_error(title="Solar MES Update Station Crossing Status Error", message=res.text)
			frappe.throw("Failed to update status: " + str(res.status_code) + " " + res.text)
	except Exception as e:
		frappe.log_error(title="Solar MES Update Station Crossing Status Exception", message=str(e))
		frappe.throw("Update Status Failed. Check Error Log: " + str(e))

def cron_fetch_and_store_mes_station_crossing_data():
	fetch_and_store_mes_station_crossing_data(run_via_cron=True)
