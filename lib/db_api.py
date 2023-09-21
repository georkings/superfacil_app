from datetime import datetime
from pymongo import MongoClient

from common_utils import save_log


class DbApi:
	def __init__(self, log_file):
		self.client = self.connect()
		self.log_file = log_file

	def connect(self):
		client = MongoClient("localhost", port=27017)
		return client

	def get_settings(self, settings_name):
		db = self.client.superfacil_app
		settings_collection = db.settings
		query = {"name": settings_name}
		return settings_collection.find_one(query)

	def get_accounts(self):
		db = self.client.superfacil_app
		accounts_collection = db.accounts
		account_list = [a for a in accounts_collection.find().sort('priority')]
		return account_list

	def update_account_session(self, email, token, cookies):
		db = self.client.superfacil_app

		accounts_collection = db.accounts
		filtering = {'email': email}

		update = {'$set': {'token': token, 'cookies_dict': cookies}}
		accounts_collection.update_one(filtering, update)

		save_log(self.log_file, f'Actualizados token y cookies de la cuenta "{email}"')

	def add_adding_timestamp(self, email):
		db = self.client.superfacil_app

		accounts_collection = db.accounts
		filtering = {'email': email}

		update = {'$set': {'added_at': datetime.now()}}
		accounts_collection.update_one(filtering, update)

		save_log(self.log_file, f'Actualizado timestamp de producto añadido de la cuenta "{email}"')

