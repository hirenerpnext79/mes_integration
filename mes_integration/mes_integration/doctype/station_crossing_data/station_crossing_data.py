import frappe
import requests
import json
from frappe.model.document import Document
from mes_integration.mes_integration.doctype.mes_configuration.mes_configuration import get_saved_mes_access_token, get_full_api_url

class StationCrossingData(Document):
	pass

@frappe.whitelist()
def fetch_and_store_mes_station_crossing_data():
	accesstoken = get_saved_mes_access_token()
	settings = frappe.get_single("MES Configuration")
		
	headers = {
		"Authorization": f"Bearer {accesstoken}",
		"Content-Type": "application/json",
		"Accept": "application/json"
	}
	
	try:
		payload = {
			"LineId": settings.line_id or "L1",
			"SiteId": settings.site_id or "31"
		}
		api_url = get_full_api_url("/api/UploadERP/GetMESStationCrossingData")
		res = requests.post(api_url, headers=headers, json=payload, verify=False, timeout=30)
		
		if res.status_code == 200:
			response_json = res.json()
			result_data = response_json.get("result", {})
			
			new_doc = frappe.new_doc("Station Crossing Data")
			new_doc.response = json.dumps(result_data, indent=4)
			
			mes_data = result_data.get("mesStationCrossingData", [])
			for item in mes_data:
				new_doc.append("work_order_and_serial_no", {
					"work_order": item.get("wO_NO"),
					"serial_no": item.get("seriaL_NO")
				})
				
			new_doc.save(ignore_permissions=True)
			
			return {"status": "success", "message": "Station Crossing Data fetched successfully"}
		else:
			frappe.log_error(title="Solar MES Fetch Station Crossing Error", message=res.text)
			frappe.throw("Failed to fetch Station Crossing Data: " + str(res.status_code) + " " + res.text)
	except Exception as e:
		frappe.log_error(title="Solar MES Fetch Station Crossing Exception", message=str(e))
		frappe.throw("Station Crossing Data Fetch Failed. Check Error Log: " + str(e))
