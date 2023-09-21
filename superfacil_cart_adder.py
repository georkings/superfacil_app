from time import perf_counter, sleep

from lib.superfacil_api import SuperFacil
from common_utils import save_log

WAIT_TIME = 0.5
STORE = 'superfacil'
SHOP_URI = 'productos-varios'
INTERVAL_TO_FETCH = 60

def fetch_sf_items(arg):
	pass

def main():
	name = 'superfacil_cart_adder'
	save_log(name, f'--- {name}.py ---')
	sf = SuperFacil(name)

	while True:
		tic = perf_counter()
		items = fetch_sf_items({'shop_uri': SHOP_URI})
		if items['items']:
			sf.cart_adder(items['items'])
			toc = perf_counter()
			if toc - tic < INTERVAL_TO_FETCH:
				sleep(INTERVAL_TO_FETCH - (toc - tic))
		sleep(WAIT_TIME)

if __name__ == '__main__':
	main()

