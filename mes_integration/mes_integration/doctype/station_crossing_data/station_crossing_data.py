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
		"Content-Type": "application/json"
	}

@frappe.whitelist()
def fetch_and_store_mes_station_crossing_data():
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
			result_data = response.get("result", {})
			
			if result_data and result_data.get("success") is False and result_data.get("msg"):
				frappe.msgprint(result_data.get("msg"), title="Station Crossing Data")
				return
				
			new_doc = frappe.new_doc("Station Crossing Data")
			new_doc.response = json.dumps(result_data, indent=4)
			
			mes_data = result_data.get("mesStationCrossingData", [])
			for item in mes_data:
				creation_date_str = item.get("creatioN_DATE", "")
				production_date = None
				production_time = None
				
				if creation_date_str:
					if "T" in creation_date_str:
						parts = creation_date_str.split("T")
					else:
						parts = creation_date_str.split(" ")
					
					if len(parts) >= 1:
						production_date = parts[0]
					if len(parts) >= 2:
						production_time = parts[1]

				new_doc.append("work_order_and_serial_no", {
					"work_order": item.get("wO_NO"),
					"serial_no": item.get("seriaL_NO"),
					"production_date_creation_date": production_date,
					"production_time_creation_date": production_time,
					"process_worker_name": item.get("workeR_NAME"),
					"qc_status_grade": item.get("grade"),
					"qc_remark_remark": item.get("remark")
				})
				
			new_doc.save(ignore_permissions=True)
			
			return {"status": "success", "message": "Station Crossing Data fetched successfully"}
		else:
			frappe.log_error(title="Solar MES Fetch Station Crossing Error", message=res.text)
			frappe.throw("Failed to fetch Station Crossing Data: " + str(res.status_code) + " " + res.text)
	except Exception as e:
		frappe.log_error(title="Solar MES Fetch Station Crossing Exception", message=str(e))
		frappe.throw("Station Crossing Data Fetch Failed. Check Error Log: " + str(e))


@frappe.whitelist()
def update_station_crossing_status_data(work_order_number):
	headers = get_mes_headers()
	settings = frappe.get_single("MES Configuration")
	
	try:
		endpoint = settings.station_crossing_status_update or "/api/UploadERP/UPdateMESStatusData"
		api_url = get_full_api_url(endpoint)
		
		# Assuming the external API expects WO_NO in the JSON payload
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
