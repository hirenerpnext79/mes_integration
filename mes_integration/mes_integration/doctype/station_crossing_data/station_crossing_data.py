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
	def validate(self):
		self.validate_and_deduplicate_serial_numbers()

	def validate_and_deduplicate_serial_numbers(self):
		latest_rows = {}
		duplicate_serials = set()
		non_serial_rows = []

		for row in self.work_order_and_serial_no or []:
			sn = (row.serial_no or "").strip()
			if not sn:
				non_serial_rows.append(row)
				continue

			if sn in latest_rows:
				duplicate_serials.add(sn)
				existing_row = latest_rows[sn]

				existing_dt = (
					str(existing_row.production_date_creation_date or ""),
					str(existing_row.production_time_creation_date or ""),
					str(existing_row.collection_date or "")
				)
				current_dt = (
					str(row.production_date_creation_date or ""),
					str(row.production_time_creation_date or ""),
					str(row.collection_date or "")
				)

				if current_dt >= existing_dt:
					latest_rows[sn] = row
			else:
				latest_rows[sn] = row

		if duplicate_serials:
			for sn in duplicate_serials:
				latest_rows[sn].is_multiple = 1

			ordered_rows = []
			seen = set()
			for row in self.work_order_and_serial_no:
				sn = (row.serial_no or "").strip()
				if not sn:
					continue
				if sn not in seen:
					ordered_rows.append(latest_rows[sn])
					seen.add(sn)

			self.work_order_and_serial_no = ordered_rows + non_serial_rows
			self.total_serial_no_count = len(self.work_order_and_serial_no)

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

def get_collection_item_sort_key(item):
	collection_date = str(item.get("collectioN_DATE") or "").strip()
	create_time = str(item.get("createTime") or "").strip()
	item_id = cint(item.get("id") or 0)
	return (collection_date, create_time, item_id)

def get_mes_item_sort_key(item):
	creation_date = str(item.get("creatioN_DATE") or item.get("createTime") or "").strip()
	update_time = str(item.get("updateTime") or "").strip()
	item_id = cint(item.get("id") or 0)
	return (creation_date, update_time, item_id)

def build_collection_map(collection_data):
	collection_map = {}
	iv_counts = {}

	for item in collection_data or []:
		serial_no = item.get("seriaL_NO")
		if not serial_no:
			continue

		clean_sn = str(serial_no).strip()
		iv_counts[clean_sn] = iv_counts.get(clean_sn, 0) + 1

		existing_item = collection_map.get(clean_sn)
		if not existing_item:
			collection_map[clean_sn] = item
		elif get_collection_item_sort_key(item) > get_collection_item_sort_key(existing_item):
			collection_map[clean_sn] = item

	return collection_map, iv_counts

def deduplicate_mes_data(mes_data):
	latest_items = {}
	counts = {}
	ordered_serials = []

	for item in mes_data or []:
		serial_no = item.get("seriaL_NO")
		if not serial_no:
			continue

		clean_sn = str(serial_no).strip()
		counts[clean_sn] = counts.get(clean_sn, 0) + 1

		if clean_sn not in latest_items:
			latest_items[clean_sn] = item
			ordered_serials.append(clean_sn)
		elif get_mes_item_sort_key(item) > get_mes_item_sort_key(latest_items[clean_sn]):
			latest_items[clean_sn] = item

	deduped_items = [latest_items[sn] for sn in ordered_serials]
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
		start_range = flt(master.get("start_range"))
		start_end = flt(master.get("start_end"))
		if start_range <= pmax_val <= start_end:
			wp = master.get("watt_pic")
			if wp is not None:
				return int(wp) if flt(wp) == int(flt(wp)) else flt(wp)
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

def mark_existing_as_multiple(existing_serials):
	if not existing_serials:
		return

	try:
		old_names = frappe.get_all(
			"MES Work Order and Serial Data",
			filters={"serial_no": ["in", list(existing_serials)], "is_multiple": 0},
			pluck="name"
		)
		for name in old_names:
			frappe.db.set_value("MES Work Order and Serial Data", name, "is_multiple", 1, update_modified=False)
	except Exception as e:
		frappe.log_error(title="MES Mark Existing Multiple Error", message=str(e))

def clear_existing_error(resolved_serials):
	if not resolved_serials:
		return

	try:
		error_names = frappe.get_all(
			"MES Work Order and Serial Data",
			filters={"serial_no": ["in", list(resolved_serials)], "error": ["is", "set"]},
			pluck="name"
		)
		for name in error_names:
			frappe.db.set_value("MES Work Order and Serial Data", name, "error", "", update_modified=False)
	except Exception as e:
		frappe.log_error(title="MES Clear Existing Error Exception", message=str(e))

def parse_station_crossing_item(item, collection_item=None, watt_pic_masters=None, is_multiple=0):
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

def prepare_station_crossing_rows(mes_data, collection_map, iv_counts, existing_serials, watt_pic_masters):
	deduped_mes_data, mes_counts = deduplicate_mes_data(mes_data)
	prepared_rows = []
	resolved_serials = []

	for item in deduped_mes_data:
		serial_no = item.get("seriaL_NO")
		clean_sn = str(serial_no).strip() if serial_no else ""
		collection_item = collection_map.get(clean_sn) if clean_sn else None

		is_multiple = 1 if (
			iv_counts.get(clean_sn, 0) > 1
			or mes_counts.get(clean_sn, 0) > 1
			or clean_sn in existing_serials
		) else 0

		try:
			row = parse_station_crossing_item(
				item,
				collection_item=collection_item,
				watt_pic_masters=watt_pic_masters,
				is_multiple=is_multiple
			)
			if clean_sn and not row.get("error") and clean_sn in existing_serials:
				resolved_serials.append(clean_sn)
		except Exception as e:
			frappe.log_error(title="Prepare Station Crossing Row Exception", message=str(e))
			row = {
				"work_order": item.get("wO_NO"),
				"serial_no": item.get("seriaL_NO"),
				"is_multiple": is_multiple,
				"error": str(e)
			}

		prepared_rows.append(row)

	if existing_serials:
		mark_existing_as_multiple(existing_serials)

	if resolved_serials:
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

		collection_map, iv_counts = build_collection_map(collection_data)

		incoming_serials = {
			str(item.get("seriaL_NO")).strip()
			for item in (mes_data or [])
			if item.get("seriaL_NO")
		}
		existing_serials = get_existing_serials(incoming_serials)
		watt_pic_masters = get_watt_pic_masters()

		crossing_rows = prepare_station_crossing_rows(
			mes_data,
			collection_map,
			iv_counts,
			existing_serials,
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
