import frappe
import requests
import json
from frappe.model.document import Document
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

@frappe.whitelist()
def fetch_and_store_iv_test_data():
	headers = get_mes_headers()
	settings = frappe.get_single("MES Configuration")
	
	try:
		endpoint = settings.iv_data or "/api/UploadERP/GetIVTestData"
		api_url = get_full_api_url(endpoint)
		res = requests.post(api_url, headers=headers, json={}, verify=False, timeout=30)
		
		if res.status_code == 200:
			response_json = res.json()
			result_data = response_json.get("result", {})
			print(result_data)
			if result_data and result_data.get("success") is False and result_data.get("msg"):
				frappe.msgprint(result_data.get("msg"), title="IV Test Data")
				return
				
			new_doc = frappe.new_doc("IV Test Data")
			new_doc.response = json.dumps(result_data, indent=4)
			new_doc.save(ignore_permissions=True)
			
			return {"status": "success", "message": "IV Test Data fetched successfully"}
		else:
			frappe.throw("Failed to fetch IV Test Data: " + str(res.status_code) + " " + res.text)
	except Exception as e:
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
			frappe.throw("Failed to update status: " + str(res.status_code) + " " + res.text)
	except Exception as e:
		frappe.throw("Update Status Failed. Check Error Log: " + str(e))
