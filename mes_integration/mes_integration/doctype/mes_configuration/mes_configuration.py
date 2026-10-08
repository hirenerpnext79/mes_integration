# Copyright (c) 2026, Mes Integration and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document


class MESConfiguration(Document):
	pass

@frappe.whitelist()
def get_mes_access_token():
	settings = frappe.get_single("MES Configuration")

	payload = {
		"account": settings.user_id,
		"password": settings.get_password("password"),
		"codeId": 0,
		"code": "string"
	}
	try:
		headers = {
			"Content-Type": "application/json",
			"Accept": "application/json"
		}
		
		login_endpoint = settings.login or "/api/sysAuth/login"
		api_url = get_full_api_url(login_endpoint)

		res = requests.post(api_url, json=payload, headers=headers, verify=False, timeout=30)
		
		data = res.json()
		if data.get("code") == 200:
			access_token = data.get("result", {}).get("accessToken")
			refresh_token = data.get("result", {}).get("refreshToken")
			time = data.get("time")
			if access_token:
				doc = frappe.get_doc("MES Configuration", "MES Configuration")
				doc.access_token = access_token
				doc.refresh_token = refresh_token
				doc.time = time
				doc.save(ignore_permissions=True)
				frappe.db.commit()
		else:
			frappe.log_error(message=res.text, title="MES Auth Status Error")
			frappe.throw("Authentication API returned error code: " + str(data.get("code")) + " - " + str(data.get("message")))
	except Exception as e:
		frappe.log_error(message=str(e), title="MES Auth Exception")
		frappe.throw("Authentication Failed. Check Error Log: " + str(e))
			
	if not access_token:
		frappe.throw("Could not get access token.")
		
	return access_token

def get_saved_mes_access_token():
	settings = frappe.get_single("MES Configuration")
	if not settings.access_token:
		frappe.throw("Access token is not available in MES Configuration. Please generate a new token.")
	return settings.access_token

def get_full_api_url(endpoint):
	settings = frappe.get_single("MES Configuration")
	base_url = settings.api_url.rstrip('/') if settings.api_url else "http://mesapi.atalsolar.com:9696"
	return f"{base_url}/{endpoint.lstrip('/')}"
