from gevent import monkey as curious_george
curious_george.patch_all(thread=False, select=False)
import grequests

import json
import requests
import telepot
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from enum import Enum
from time import perf_counter, sleep

from common_utils import save_log, save_content, send_whatsapp

from .db_api import DbApi

HEADERS = {
	'user-agent': 'Mozilla/5.0 (Linux; Android 10; Pixel 4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36'
}


class AccountStatus(Enum):
	PAID = 'paid'              # link from TM was already gotten
	ADDED = 'added'            # item was added to cart
	MAYBE = 'maybe'            # maybe item was added to cart, it needs to be checked
	DONE = 'done'              # item was not added to cart
	TODO = 'todo'
	LOGGEDOUT = 'loggedout'


class Account:
	def __init__(self, email, password, token, cookies_dict, added_at, contact, transfermovil_phone):
		self.email = email
		self.password = password
		self.token = token
		self.cookies_dict = cookies_dict
		self.added_at = added_at
		self.contact = contact
		self.transfermovil_phone = transfermovil_phone
		self.status = AccountStatus.TODO

	def to_json(self):
		return {
		        '_token': self.token,
			'email': self.email,
			'password': self.password,
		}

	@staticmethod
	def from_json(json):
		if json is None: return None
		return Account(
			json['email'],
			json['password'],
			json['token'] if 'token' in json else "",
			json['cookies_dict'] if 'cookies_dict' in json else {},
			json['added_at'] if 'added_at' in json else None,
			json['contact'] if 'contact' in json else None,
			json['transfermovil_phone'] if 'transfermovil_phone' in json else None,
		)

	def __str__(self):
		return f'Cuenta: "{self.email}"'


class Contact:
	def __init__(self, name, value):
		self.name = name
		self.value = value

	def __str__(self):
		return f'{{name: {self.name}, value: {self.value}}}'


class CartItem:
	def __init__(self, product_title, quantity, price):
		self.product_title = product_title
		self.quantity = quantity
		self.price = price

	def __str__(self):
		return f'{{title: {self.product_title}, quantity: {self.quantity}, price: {self.price}}}'


WAIT_TIME_TO_RELOGIN = 25
WAIT_TIME = 10
TIMEOUT_VALUE = 90
INTERVAL_BETWEEN_REQUESTS = 15
RETRIES_BY_DEFAULT = 3
HOST_SUPERFACIL = "www.superfacil.net"
PHONE_WHITELIST = ['+5353545737', '+5352519445', '+5353172683']


class SuperFacil:
	def __init__(self, name):
		self.log_file = name
		self.db_api = DbApi(self.log_file)
		adder_settings = self.db_api.get_settings("general")
		self.retries = RETRIES_BY_DEFAULT if adder_settings == None else adder_settings['RETRIES']
	
	def save_log_wrapper(self, message):
		save_log(self.log_file, message)

	def handle_exception(self, ex):
		self.save_log_wrapper('$$$$$$$$$$$$$$ Exception $$$$$$$$$$$$$')
		self.save_log_wrapper(str(ex))
		return False

	def extract_token(self, content):
		soup = BeautifulSoup(content, 'html.parser')
		results = soup.findAll('meta', {'name': 'csrf-token'})
		if not len(results):
			return ""
		csrf_token = results[0]
		if not csrf_token.has_attr('content'):
			return ""
		return csrf_token.attrs['content']

	def login(self, account):
		s = requests.Session()
		login_url = f"https://{HOST_SUPERFACIL}/acceder"
		try:
			response = s.get(login_url, headers=HEADERS, timeout=TIMEOUT_VALUE)
		except Exception as ex:
			return self.handle_exception(ex)
		self.save_log_wrapper('LOGIN GET STATUS_CODE: ' + str(response.status_code))
		if response.status_code != 200:
			return False
		token = self.extract_token(response.content)
		self.save_log_wrapper('csrf-token: ' + token)
		# save_content(self.log_file, response.content, 'login_get')
		if not token:
			return False

		account.token = token
		try:
			response = s.post(login_url, data=account.to_json(), headers=HEADERS, timeout=TIMEOUT_VALUE)
		except Exception as ex:
			return self.handle_exception(ex)
		self.save_log_wrapper('LOGIN POST STATUS_CODE: ' + str(response.status_code))
		if response.status_code != 200:
			return False
		token = self.extract_token(response.content)
		self.save_log_wrapper('csrf-token: ' + token)
		# save_content(self.log_file, response.content, 'login_post')
		if not token:
			return False
		self.update_account_session(account.email, token, s.cookies.get_dict())
		return True

	def login_wrapper(self, account):
		for i in range(self.retries):
			if self.login(account):
				break

	def update_account_session(self, email, token, cookies_dict):
		for a in self.accounts:
			if a.email == email:
				a.token = token
				a.cookies_dict = cookies_dict
				self.db_api.update_account_session(email, token, cookies_dict)
				break

	def extract_user(self, content):
		soup = BeautifulSoup(content, 'html.parser')
		result = soup.find(class_='user-name')
		if result is None:
			return ""
		return result.get_text().strip()

	def check_login(self, account):
		if not account.token:
			return self.login(account)
		s = requests.Session()
		s.cookies.update(account.cookies_dict)
		home_url = f"https://{HOST_SUPERFACIL}/"
		try:
			response = s.get(home_url, headers=HEADERS, timeout=TIMEOUT_VALUE)
		except Exception as ex:
			return self.handle_exception(ex)
		self.save_log_wrapper('HOME STATUS_CODE: ' + str(response.status_code))
		if response.status_code != 200:
                        return False
		# save_content(self.log_file, response.content, 'home')

		user = self.extract_user(response.content)
		if user:
			self.save_log_wrapper(user)
			return True
		else:
			self.save_log_wrapper("Usuario no logueado")
			return self.login(account)

	def logins_checker(self):
		self.get_accounts_from_DB()
		for a in self.accounts:
			self.save_log_wrapper(a)
			# if a.added_at is not None:
			#	if datetime.now() - a.added_at < timedelta(minutes=WAIT_TIME_TO_RELOGIN):
			#		self.save_log_wrapper("Producto añadido recientemente")
			#		continue
			for i in range(3):
				if self.check_login(a):
					break
				sleep(1)
			sleep(1)

			# return

	def check_success_adding(self, content, product_list):
		soup = BeautifulSoup(content, 'html.parser')
		result = soup.find(class_='success-add')
		list_log =  ''.join([f'[{product}]' for product in product_list])
		if result is None:
			self.save_log_wrapper('[INFO]' + list_log + ' Producto no añadido')
			save_content(self.log_file, content, 'add_to_cart')
			return False
		self.save_log_wrapper('[INFO]' + list_log + ' Producto añadido exitosamente!!!')
		return True

	def get_content_to_share(self, item_dict_list):
		header = "\U0001F6D2\U00000031\U0000FE0F\U000020E3 Producto Agregado \U0001F973\U0001F60E"
		datetimenow = datetime.now()
		datenow = "\U0001F5D3 Fecha: " + datetimenow.strftime('%Y-%m-%d')
		timenow = "\U0000231A Hora: " + datetimenow.strftime('%H:%M:%S')
		shop_title = "\U0001F4A2 Tienda: " + item_dict_list[0]["shop_title"]
		products = "\U0001F6CD Producto(s): " + ', '.join( \
		           [f"{item_dict['product_title']} (${float(item_dict['price']):0.2f} CUP)" for item_dict in item_dict_list])
		account_text = "\U0001F464 Cuentas: " + ','.join([a.email for a in self.accounts if a.status == AccountStatus.ADDED])
		banner = "Cortesía de Superfacil App \U0001F609"

		shared_content = f"{header}\n{datenow}\n{timenow}\n{shop_title}\n{products}\n{account_text}\n\n{banner}"
		return shared_content

	def check_if_region_OK(self, item_dict):
		return 'provinces' in item_dict and any(element['region_id'] == '36' for element in item_dict['provinces'])

	def update_account_status(self, account, status):
		for a in self.accounts:
			if a.email == account.email:
				a.status = status
				break

	def process_adding_response(self, response, account, product_list):
		self.save_log_wrapper(f"[INFO] Cuenta: " + account.email)
		if isinstance(response, Exception):
			self.save_log_wrapper(str(response))
			return
		if response is None:
			self.save_log_wrapper('[WARNING] Failed to get response')
			return
		self.save_log_wrapper('[INFO] CART STATUS_CODE: ' + str(response.status_code))
		if response.status_code == 419 or response.request.url == f'https://{HOST_SUPERFACIL}/acceder':
			self.login_wrapper(account)
			# self.update_account_status(account, AccountStatus.LOGGEDOUT)
			return
		# save_content(self.log_file, response.content, 'add_to_cart_' + account.email.split('@')[0])
		if response.status_code != 200:
			return
		if self.check_success_adding(response.content, product_list):
			self.db_api.add_adding_timestamp(account.email)
			self.update_account_status(account, AccountStatus.ADDED)
		elif len(product_list) > 1:
			self.update_account_status(account, AccountStatus.MAYBE)
		else:
			self.update_account_status(account, AccountStatus.DONE)

	def cart_adder(self, item_dict_list, isittest=False):
		def exception_handler(request, exception):
			return exception
		if not any(self.check_if_region_OK(item_dict) for item_dict in item_dict_list):
			self.save_log_wrapper(f"[INFO] Producto(s) no disponible(s) en municipio deseado")
			return
		self.save_log_wrapper(f"[INFO] Producto(s) disponible(s), se intentará(n) añadir")

		self.get_accounts_from_DB(isittest)
		cart_url = f"https://{HOST_SUPERFACIL}/{item_dict_list[0]['shop_uri']}/cesta"
		post_headers={**HEADERS, 'referer': f"https://{HOST_SUPERFACIL}/{item_dict_list[0]['shop_uri']}"}
		tic = None
		for i in range(self.retries):
			self.save_log_wrapper("[INFO] Retry #" + str(i+1))
			toc = perf_counter()
			if tic is not None and toc - tic < INTERVAL_BETWEEN_REQUESTS:
				sleep(INTERVAL_BETWEEN_REQUESTS - (toc - tic) + 1)
			tic = perf_counter()

			to_do_accounts = [a for a in self.accounts if a.status == AccountStatus.TODO]
			# generate requests
			reqs = []
			for account in to_do_accounts:
				s = requests.Session()
				s.cookies.update(account.cookies_dict)

				print('cart_adder cookies: ' + str(account.cookies_dict))

				account.session = s
				form_data = {'_token': (None, account.token)}
				for item_dict in item_dict_list:
					if self.check_if_region_OK(item_dict):
						form_data[f'products[{item_dict["product_field_id"]}]'] = (None, '0')
						form_data[f'products[{item_dict["product_field_id"]}][quantity]'] = (None, '1')
						form_data[f'products[{item_dict["product_field_id"]}][properties][region_id]'] = (None, '36')

				reqs.append(grequests.post(cart_url, session=s, files=form_data, headers=post_headers, timeout=TIMEOUT_VALUE))
			# map
			responses = grequests.map(reqs, exception_handler=exception_handler)
			# process response
			for i, r in enumerate(responses):

				print(r.request.headers)

				self.process_adding_response(r, to_do_accounts[i], [item_dict["product_title"] for item_dict in item_dict_list])

			if not any(a.status != AccountStatus.ADDED and a.status!= AccountStatus.MAYBE and a.status!= AccountStatus.DONE for a in self.accounts):
				break

		if any(a.status == AccountStatus.ADDED for a in self.accounts) and not isittest:
			shared_content = self.get_content_to_share(item_dict_list)
			send_whatsapp(shared_content, self.log_file, PHONE_WHITELIST)

		return
		for i in range(self.retries):
			accounts_to_check_payment = [a for a in self.accounts if a.status == AccountStatus.ADDED or a.status == AccountStatus.MAYBE]
			for account in accounts_to_check_payment:
				self.payment(account, item_dict_list[0]['shop_uri'])


				return

	def get_accounts_from_DB(self, isittest=False):
		account_json_list = self.db_api.get_accounts()
		if isittest:
			account_json_list = account_json_list[:1]
		self.accounts = [Account.from_json(ajl) for ajl in account_json_list]
		self.save_log_wrapper(f"{len(self.accounts)} cuenta(s) encontrada(s)")

	def search_items_for_testing(self, shop_uri):
		shop_url = f"https://{HOST_SUPERFACIL}/{shop_uri}"
		print(shop_url)
		try:
			response = requests.get(shop_url, headers=HEADERS, timeout=TIMEOUT_VALUE)
		except Exception as ex:
			print(ex)
			return

		print('SHOP STATUS_CODE: ' + str(response.status_code))
		if response.status_code != 200:
			return
		return self.process_search_items_response(response.content, shop_uri)

	def process_search_items_response(self, content, shop_uri):
		soup = BeautifulSoup(content, 'html.parser')
		product_box_list = soup.findAll(class_='product-box')
		if not product_box_list:
			return []
		item_dict_list = []
		shop_title = soup.find('title').get_text().strip()
		for product_box in product_box_list:

			product_title = product_box.find(class_='product-name').get_text().strip()

			form_control = product_box.find(class_='form-control')
			if not form_control.has_attr('name'):
			        continue
			product_field_id = form_control.attrs['name'].split('products[')[1].split('][quantity]')[0]

			price_text = product_box.find(class_='prod-price').get_text().replace(',', '').strip().split()[0]
			price = float(price_text)

			provinces_option_list = product_box.findAll('option')
			provinces = [{'region_id': provinces_option.attrs['value'], 'name': provinces_option.get_text().strip()} for provinces_option in provinces_option_list]
			if not self.check_if_region_OK({'provinces': provinces}):
				continue

			item_dict = {
				'product_title': product_title,
				'product_field_id': product_field_id,
				'shop_title': shop_title,
				'shop_uri': shop_uri,
				'price': price,
				'provinces': provinces,
			}
			item_dict_list.append(item_dict)

		return item_dict_list

	def payment(self, account, shop_uri):
		self.save_log_wrapper(f"*** PAYMENT - {account.email} ***")
		if account.transfermovil_phone is None:
			self.update_account_status(account, AccountStatus.DONE)
			self.save_log_wrapper(f"Esta cuenta no tiene configurado teléfono de TM")
			return

		# GET to cesta/
		step1_output = self.payment_request(
			account,
			1,
			f"https://{HOST_SUPERFACIL}/{shop_uri}/cesta",
			{'referer': f"https://{HOST_SUPERFACIL}/{shop_uri}"},
			account.session.get,
			self.process_step1_response,
		)
		if step1_output is None:
			return

		# POST selecting recipient
		account.contactId = self.get_contactId(account)
		self.save_log_wrapper("contactId: " + account.contactId)
		step2_output = self.payment_request(
			account,
			2,
			f"https://{HOST_SUPERFACIL}/{shop_uri}/cesta/deliver-options",
			{'referer': f"https://{HOST_SUPERFACIL}/{shop_uri}/cesta", 'x-requested-with': 'XMLHttpRequest'},
			account.session.post,
			self.process_step2_response,
			http_args={'data': {'_token': account.token, 'contactId': account.contactId}},
		)
		if step2_output is None:
			return

		# PUT with delivery option selected
		step3_output = self.payment_request(
			account,
			3,
			f"https://{HOST_SUPERFACIL}/{shop_uri}/cesta/deliver-options/{account.deliverOptionId}",
			{'referer': f"https://{HOST_SUPERFACIL}/{shop_uri}/cesta", 'x-requested-with': 'XMLHttpRequest'},
			account.session.put,
			self.process_step3_response,
			http_args={'data': {'_token': account.token, 'deliverOptionId': account.deliverOptionId}},
		)
		if step3_output is None:
			return

		step5_output = self.payment_request(
			account,
			5,
			f"https://{HOST_SUPERFACIL}/{shop_uri}/pagos",
			{'referer': f"https://{HOST_SUPERFACIL}/{shop_uri}/cesta", 'x-requested-with': 'XMLHttpRequest'},
			account.session.post,
			self.process_step5_response,
			http_args={},
		)

		# final POST to get TM payment link
		sleep(1)
		step4_data = self.get_step4_data(account)
		step4_output = self.payment_request(
			account,
			4,
			f"https://{HOST_SUPERFACIL}/{shop_uri}/pagos",
			{'referer': f"https://{HOST_SUPERFACIL}/{shop_uri}/cesta"},
			account.session.post,
			self.process_step4_response,
			http_args={'files': step4_data},
		)
		if step4_output is None:
			return

	def payment_request(self, account, step_number, url, step_headers, http_method, process_payment_response, http_args={}):
		s = requests.Session()
		s.cookies.update(account.cookies_dict)

		self.save_log_wrapper(f"*** STEP {step_number} ***")
		payment_headers = {**HEADERS, **step_headers}
		i = 0
		while i < self.retries:
			self.save_log_wrapper("[INFO] Retry #" + str(i+1))
			try:
				# response = http_method(url, headers=payment_headers, timeout=TIMEOUT_VALUE, **http_args)
				if step_number == 1:
					response = s.get(url, headers=payment_headers, timeout=TIMEOUT_VALUE, **http_args)
				elif step_number == 2:
					response = s.post(url, headers=payment_headers, timeout=TIMEOUT_VALUE, **http_args)
				elif step_number == 3:
					response = s.put(url, headers=payment_headers, timeout=TIMEOUT_VALUE, **http_args)
				elif step_number == 5:
					step5_data = {
						'_token': account.token,
						'contact': account.contactId,
						'delivery': account.deliverOptionId,
						'transfermovil_phone:': account.transfermovil_phone,
						'merchant': '33002',
						'cart-quantity': account.cart_item_list[0].quantity,
						'_jsvalidation': 'delivery',
						'_jsvalidation_validate_all': 'false',
					}
					response = s.post(url, headers=payment_headers, timeout=TIMEOUT_VALUE, data=step5_data)
				elif step_number == 4:
					step4_data = self.get_step4_data(account)
					response = s.post(url, headers=payment_headers, timeout=TIMEOUT_VALUE, files=step4_data)
				# if step_number !=4:
				self.update_account_session(account.email, account.token, s.cookies.get_dict())
				print(response.request.headers)
			except Exception as ex:
				self.handle_exception(ex)
				sleep(1)
				continue
			self.save_log_wrapper(f'STEP {step_number} STATUS_CODE: ' + str(response.status_code))
			if response.status_code == 429:
				sleep(WAIT_TIME)
				continue
			if response.status_code == 419 or response.request.url == f'https://{HOST_SUPERFACIL}/acceder':
				self.login_wrapper(account)
				return
			i += 1
			if response.status_code != 200:
				continue
			if self.is_cart_empty(response.content, account):
				self.save_log_wrapper("Carrito vacío")
				self.update_account_status(account, AccountStatus.DONE)
				return
			return process_payment_response(response.content, account)

	def is_cart_empty(self, content, account):
		soup = BeautifulSoup(content, 'html.parser')
		main = soup.find(id='main')
		return main is not None and "No tiene elementos en su carrito de compras" in main.get_text().strip()

	def process_step1_response(self, content, account):
		soup = BeautifulSoup(content, 'html.parser')

		contacts_tag = soup.find(id='contacts')
		if contacts_tag is None:
			self.save_log_wrapper("No hay etiqueta con id='contacts'")
			return
		option_tag_list = contacts_tag.findAll('option')
		contact_list = []
		for tag in option_tag_list:
			name = tag.get_text().strip()
			if not name:
				continue
			if not tag.has_attr('value'):
				continue
			value = tag.attrs['value']
			if not value:
				continue
			contact_list.append(Contact(name, value))
		if not contact_list:
			return
		self.save_log_wrapper("CONTACTS: " + ', '.join([str(contact) for contact in contact_list]))
		account.contact_list = contact_list

		prod_item_info_list = soup.findAll('div', class_='table-row prod-item-info')
		cart_item_list = []
		for prod_item_info in prod_item_info_list:
			product_title_div = prod_item_info.find('div', class_='table-cell product-title')
			if product_title_div is None:
				return
			product_title_p = product_title_div.find('p')
			if product_title_p is None:
				return
			product_title = product_title_p.get_text().strip()
			if not product_title:
				return

			quantity_div = prod_item_info.find('div', class_='quantity')
			if quantity_div is None:
				return
			quantity_input = quantity_div.find('input')
			if quantity_input is None:
				return
			if not quantity_input.has_attr('value'):
				return
			quantity = quantity_input.attrs['value']
			if not quantity:
				return

			price_div = prod_item_info.find('div', class_='table-cell product-total')
			if price_div is None:
				return
			price = price_div.get_text().strip()
			if not price:
				return

			cart_item_list.append(CartItem(product_title, quantity, price))
		if not cart_item_list:
			return
		self.save_log_wrapper("CART: " + ', '.join([str(cart_item) for cart_item in cart_item_list]))
		account.cart_item_list = cart_item_list

		return True

	def get_contactId(self, account):
		for contact in account.contact_list:
			if contact.name == account.contact:
				return contact.value
		self.contact = account.contact_list[0].name
		return account.contact_list[0].value

	def process_step2_response(self, content, account):
		soup = BeautifulSoup(content, 'html.parser')
		input_tag = soup.find('input')
		if input_tag is None:
			return
		if not input_tag.has_attr('data-deliver_option_id'):
			return
		deliverOptionId = input_tag.attrs['data-deliver_option_id']
		if not deliverOptionId:
			return
		self.save_log_wrapper("deliverOptionId: " + deliverOptionId)
		account.deliverOptionId = deliverOptionId
		return True

	def process_step3_response(self, content, account):
		try:
			rjson = json.loads(content)
		except json.decoder.JSONDecodeError as ex:
			return
		if not 'total' in rjson or not 'shipmentCost' in rjson:
			return
		self.save_log_wrapper(f"total: {rjson['total']}, shipmentCost: {rjson['shipmentCost']}")
		account.total = rjson['total']
		account.shipmentCost = rjson['shipmentCost']
		return True

	def get_step4_data(self, account):
		step4_data = {
			'_token': (None, account.token),
			'contact': (None, account.contactId),
			'delivery': (None, account.deliverOptionId),
			'transfermovil_phone:': (None, account.transfermovil_phone),
			'merchant': (None, '33002'),
			'cart-quantity': (None, account.cart_item_list[0].quantity),
		}
		print(step4_data)
		return step4_data
		#for cart_item in account.cart_item_list:
		#	step4_data[]

	def process_step4_response(self, content, account):
		save_content(self.log_file, content, 'step4_data')
		soup = BeautifulSoup(content, 'html.parser')

	def process_step5_response(self, content, account):
		self.save_log_wrapper(content)

