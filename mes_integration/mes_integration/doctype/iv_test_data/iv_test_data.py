import frappe
import requests
import json
from frappe.model.document import Document
from mes_integration.mes_integration.doctype.mes_configuration.mes_configuration import get_saved_mes_access_token, get_full_api_url

class IVTestData(Document):
	pass

@frappe.whitelist()
def fetch_and_store_iv_test_data():
	accesstoken = get_saved_mes_access_token()
	settings = frappe.get_single("MES Configuration")
		
	headers = {
		"Authorization": f"Bearer {accesstoken}",
		"Content-Type": "application/json"
	}
	
	try:
		api_url = get_full_api_url("/api/UploadERP/GetIVTestData")
		res = requests.post(api_url, headers=headers, json={}, verify=False, timeout=30)
		
		if res.status_code == 200:
			response_json = res.json()
			result_data = response_json.get("result", {})
			
			if result_data and result_data.get("success") is False and result_data.get("msg"):
				frappe.msgprint(result_data.get("msg"), title="IV Test Data")
				return
				
			new_doc = frappe.new_doc("IV Test Data")
			new_doc.response_data = json.dumps(result_data, indent=4)
			new_doc.save(ignore_permissions=True)
			
			return {"status": "success", "message": "IV Test Data fetched successfully"}
		else:
			frappe.log_error(title="Solar MES Fetch IV Data Error", message=res.text)
			frappe.throw("Failed to fetch IV Test Data: " + str(res.status_code) + " " + res.text)
	except Exception as e:
		frappe.log_error(title="Solar MES Fetch IV Data Exception", message=str(e))
		frappe.throw("IV Data Fetch Failed. Check Error Log: " + str(e))
