import os
from pathlib import Path
from time import perf_counter, sleep

from lib.superfacil_api import SuperFacil
from cnc_db import Client
from superfacil_db import Fetch
from common_utils import save_log

os.chdir('/opt/cnc-backend/')

WAIT_TIME = 0.5
STORE = 'superfacil'
SHOP_URI = 'productos-varios'
INTERVAL_TO_FETCH = 60

def main():
	name = 'superfacil_cart_adder'
	save_log(name, f'--- {name}.py ---')
	sf = SuperFacil(name)

	client_db = Client(STORE, SHOP_URI)
	item_db = Fetch(client_db)

	while True:
		tic = perf_counter()
		items = item_db.fetch_items({'shop_uri': SHOP_URI})
		if items['items']:
			sf.cart_adder(items['items'])
			toc = perf_counter()
			if toc - tic < INTERVAL_TO_FETCH:
				sleep(INTERVAL_TO_FETCH - (toc - tic))
		sleep(WAIT_TIME)

if __name__ == '__main__':
	main()

