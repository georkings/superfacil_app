from time import sleep

from lib.superfacil_api import SuperFacil
from common_utils import save_log

WAIT_TIME = 540

def main():
	name = 'superfacil_login_checker'
	save_log(name, f'--- {name}.py ---')
	sf = SuperFacil(name)
	while True:
		try:
			sf.logins_checker()
		except Exception as ex:
			save_log(name, str(ex))
		sleep(WAIT_TIME)

if __name__ == '__main__':
	main()

