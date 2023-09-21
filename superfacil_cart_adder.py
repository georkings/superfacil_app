from lib.superfacil_api import SuperFacil

import json
import requests
from time import perf_counter, sleep

from common_utils import save_log

headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ChromeNC/78.0.3904.70 Safari/537.36'
}

WAIT_TIME = 0.5
SERVER_URL = 'srv27118-206152.vps.etecsa.cu'
STORE = 'superfacil'
SHOP_URI = 'productos-varios'
INTERVAL_TO_FETCH = 60

def fetch_sf_items(log_file, shop_uri):
	fetch_url = f'http://{SERVER_URL}:5000/superfacil/fetch/'
	body_dict = {
		'store': STORE,
		'shop_uri': shop_uri,
	}

	try:
		response = requests.post(fetch_url, json=body_dict, headers=headers)
	except Exception as ex:
		save_log(log_file, str(ex))

	if response.status_code == 200:
		rjson = response.json()
		try:
			items = json.loads(rjson)
		except json.decoder.JSONDecodeError as ex:
			return
		if not 'items' in items:
			save_log(log_file, items)
			sleep(WAIT_TIME)
			return
		return items
	save_log(log_file, 'server fetch STATUS: ' + str(response.status_code))

	return

def main():
	name = 'superfacil_cart_adder'
	save_log(name, f'--- {name}.py ---')
	# sf = SuperFacil(name)

	while True:
		tic = perf_counter()
		items = fetch_sf_items(name, SHOP_URI)
		if items is not None and items['items']:
			save_log(name, items['items'])
			# sf.cart_adder(items['items'])
			toc = perf_counter()
			if toc - tic < INTERVAL_TO_FETCH:
				sleep(INTERVAL_TO_FETCH - (toc - tic))
		sleep(WAIT_TIME)

if __name__ == '__main__':
	main()

