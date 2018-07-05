import json
import os

import requests
from flask_testing import TestCase

from server.influx.cq import backfill_login_measurements


class AbstractTest(TestCase):

    def create_app(self):
        from server.__main__ import main
        os.environ["TEST"] = "1"
        app = main("config/test_config.yml")
        config = app.app_config
        config.test = True
        db = app.influx_client

        databases = list(map(lambda p: p["name"], db.get_list_database()))
        db_name = config.database.name
        if db_name not in databases or self.force_init_database():
            self.init_database(db, config, db_name)
        return app

    def force_init_database(self):
        return False

    @staticmethod
    def init_database(db, config, db_name):
        db.drop_database(db_name)
        db.create_database(db_name)
        db.switch_database(db_name)
        file = f"{os.path.dirname(os.path.realpath(__file__))}/seed/seed.json"
        with open(file) as f:
            json_body = json.loads(f.read())
            db.write_points(json_body)

        backfill_login_measurements(config, db)

    def get(self, url, query_data={}, response_status_code=200, api="stats"):
        with requests.Session():
            response = self.client.get(f"/api/{api}/{url}",
                                       headers={"Authorization": "Basic ZGFzaGJvYXJkOnNlY3JldA=="},
                                       query_string=query_data)
            self.assertEqual(response_status_code, response.status_code, msg=str(response.json))
            return response.json

    @staticmethod
    def read_file(path):
        file = f"{os.path.dirname(os.path.realpath(__file__))}/{path}"
        with open(file) as f:
            return f.read()
