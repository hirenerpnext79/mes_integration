import json
import frappe
import requests
from frappe.model.document import Document
from frappe.utils import cint, flt
from mes_integration.mes_integration.doctype.mes_configuration.mes_configuration import (
	get_full_api_url,
	get_saved_mes_access_token
)

class StationCrossingData(Document):
	pass

def get_mes_headers():
	accesstoken = get_saved_mes_access_token()
	return {
		"Authorization": f"Bearer {accesstoken}",
		"Content-Type": "application/json",
		"Accept": "application/json"
	}

def post_mes_request(endpoint, payload=None, timeout=30):
	api_url = get_full_api_url(endpoint)
	return requests.post(
		api_url,
		headers=get_mes_headers(),
		json=payload or {},
		verify=False,
		timeout=timeout
	)

def parse_production_datetime(date_string):
	if not date_string:
		return None, None

	parts = str(date_string).replace("T", " ").split(maxsplit=1)
	if not parts:
		return None, None
	return (parts[0], parts[1]) if len(parts) > 1 else (parts[0], None)

def get_collection_item_sort_key(item):
	return (
		str(item.get("collectioN_DATE") or "").strip(),
		str(item.get("createTime") or "").strip(),
		cint(item.get("id") or 0)
	)

def get_mes_item_sort_key(item):
	return (
		str(item.get("creatioN_DATE") or item.get("createTime") or "").strip(),
		str(item.get("updateTime") or "").strip(),
		cint(item.get("id") or 0)
	)

def _deduplicate_by_serial(data, sort_key_fn):
	latest_records = {}
	counts = {}

	for item in data or []:
		serial_no = item.get("seriaL_NO")
		if not serial_no:
			continue

		clean_sn = str(serial_no).strip()
		counts[clean_sn] = counts.get(clean_sn, 0) + 1
		sort_key = sort_key_fn(item)

		existing = latest_records.get(clean_sn)
		if not existing or sort_key > existing[0]:
			latest_records[clean_sn] = (sort_key, item)

	return latest_records, counts

def build_collection_map(collection_data):
	latest_records, counts = _deduplicate_by_serial(collection_data, get_collection_item_sort_key)
	collection_map = {sn: item for sn, (_, item) in latest_records.items()}
	return collection_map, counts

def deduplicate_mes_data(mes_data):
	latest_records, counts = _deduplicate_by_serial(mes_data, get_mes_item_sort_key)
	deduped_items = [item for _, item in latest_records.values()]
	return deduped_items, counts

def get_watt_pic_masters():
	try:
		return frappe.get_all(
			"MES Watt Pic Master",
			fields=["start_range", "start_end", "watt_pic"],
			order_by="start_range asc"
		)
	except Exception as e:
		frappe.log_error(title="MES Watt Pic Master Load Error", message=str(e))
		return []

def match_watt_pic(pmax, watt_pic_masters):
	if pmax is None or not watt_pic_masters:
		return None

	pmax_val = flt(pmax)
	for master in watt_pic_masters:
		if flt(master.get("start_range")) <= pmax_val <= flt(master.get("start_end")):
			wp = master.get("watt_pic")
			if wp is not None:
				wp_flt = flt(wp)
				return int(wp_flt) if wp_flt.is_integer() else wp_flt
	return None

def get_existing_serials(serial_numbers):
	if not serial_numbers:
		return set()

	try:
		return set(frappe.get_all(
			"MES Work Order and Serial Data",
			filters={"serial_no": ["in", list(serial_numbers)]},
			pluck="serial_no"
		))
	except Exception as e:
		frappe.log_error(title="MES Fetch Existing Serials Error", message=str(e))
		return set()

def update_existing_serial_records(filters, fieldname, value, error_title):
	try:
		frappe.db.set_value(
			"MES Work Order and Serial Data",
			filters,
			fieldname,
			value,
			update_modified=False
		)
	except Exception as e:
		frappe.log_error(title=error_title, message=str(e))

def mark_existing_as_multiple(existing_serials):
	if existing_serials:
		update_existing_serial_records(
			{"serial_no": ["in", list(existing_serials)], "is_multiple": 0},
			"is_multiple",
			1,
			"MES Mark Existing Multiple Error"
		)

def clear_existing_error(resolved_serials):
	if resolved_serials:
		update_existing_serial_records(
			{"serial_no": ["in", list(resolved_serials)], "error": ["is", "set"]},
			"error",
			"",
			"MES Clear Existing Error Exception"
		)

def parse_station_crossing_item(item, collection_item=None, watt_pic_masters=None, is_multiple=0, serial_no=None):
	production_date, production_time = parse_production_datetime(
		item.get("creatioN_DATE")
	)
	clean_sn = serial_no if serial_no is not None else str(item.get("seriaL_NO") or "").strip()

	row = {
		"work_order": item.get("wO_NO"),
		"serial_no": clean_sn,
		"production_date_creation_date": production_date,
		"production_time_creation_date": production_time,
		"process_worker_name": item.get("workeR_NAME"),
		"qc_status_grade": item.get("grade"),
		"qc_remark_remark": item.get("remark"),
		"cell_location_errorposition": item.get("errorPosition"),
		"module_defect_code_errorcode": item.get("errorCode"),
		"is_multiple": 1 if is_multiple else 0,
		"error": "",
		"collection_date": None
	}

	if not collection_item:
		row["error"] = "IV data not found for serial number"
		return row

	pmax = flt(collection_item.get("pmax"))
	matched_watt_pic = match_watt_pic(pmax, watt_pic_masters)
	watt_pic = matched_watt_pic if matched_watt_pic is not None else collection_item.get("powerLevel")

	row.update({
		"pmax": pmax,
		"isc": flt(collection_item.get("isc")),
		"voc": flt(collection_item.get("voc")),
		"ipm": flt(collection_item.get("ipm")),
		"vpm": flt(collection_item.get("vpm")),
		"ff": flt(collection_item.get("ff")),
		"eff": flt(collection_item.get("eff")),
		"watt_pic": watt_pic,
		"current": collection_item.get("currentLevel"),
		"collection_date": collection_item.get("collectioN_DATE")
	})

	if matched_watt_pic is None and pmax > 0:
		row["error"] = f"Watt Pic range not found for Pmax {pmax} in MES Watt Pic Master"
	elif not pmax:
		row["error"] = "Pmax missing or invalid in IV data"

	return row

def prepare_station_crossing_rows(mes_data, collection_map, iv_counts, watt_pic_masters, existing_serials=None):
	deduped_mes_data, mes_counts = deduplicate_mes_data(mes_data)
	if existing_serials is None:
		existing_serials = get_existing_serials(mes_counts.keys())

	prepared_rows = []
	resolved_serials = []

	for item in deduped_mes_data:
		clean_sn = str(item.get("seriaL_NO") or "").strip()
		collection_item = collection_map.get(clean_sn) if clean_sn else None
		is_existing = clean_sn in existing_serials

		is_multiple = int(
			iv_counts.get(clean_sn, 0) > 1
			or mes_counts.get(clean_sn, 0) > 1
			or is_existing
		)

		try:
			row = parse_station_crossing_item(
				item,
				collection_item=collection_item,
				watt_pic_masters=watt_pic_masters,
				is_multiple=is_multiple,
				serial_no=clean_sn
			)
			if clean_sn and is_existing and not row.get("error"):
				resolved_serials.append(clean_sn)
		except Exception as e:
			frappe.log_error(title="Prepare Station Crossing Row Exception", message=str(e))
			row = {
				"work_order": item.get("wO_NO"),
				"serial_no": clean_sn,
				"is_multiple": is_multiple,
				"error": str(e)
			}

		prepared_rows.append(row)

	mark_existing_as_multiple(existing_serials)
	clear_existing_error(resolved_serials)

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
		res = post_mes_request(endpoint, payload)

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

		collection_map, iv_counts = build_collection_map(collection_data)
		watt_pic_masters = get_watt_pic_masters()

		crossing_rows = prepare_station_crossing_rows(
			mes_data,
			collection_map,
			iv_counts,
			watt_pic_masters
		)

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
		res = post_mes_request(endpoint, {"WO_NO": work_order_number})

		if res.status_code != 200:
			frappe.log_error(title="Solar MES Update Station Crossing Status Error", message=res.text)
			frappe.throw(f"Failed to update status: {res.status_code} {res.text}")

		data = res.json() or {}
		result = data.get("result") or {}
		msg = result.get("message") or data.get("message")
		is_success = result.get("success", data.get("success", True))

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
