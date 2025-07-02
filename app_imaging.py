import requests

from flask import Config as FlaskConfig
from app_logger import AppLogger

class AppImaging:
    def __init__(self, app_logger: AppLogger, config: FlaskConfig):
        self.base_url = f"{config["IMAGING_URL"]}rest/tenants"
        self.params = {"api-key": config["IMAGING_API_KEY"]}
        self.app_logger = app_logger

    def get_source_locations(self, tenant, application, object_id):
        object_url = f"{self.base_url}/{tenant}/applications/{application}/objects/{object_id}?select=source-locations"
        return requests.get(object_url, params=self.params, verify=False), object_url

    def get_source(self, object_type, tenant, application, object_id,  start_line, end_line, request_id):
        object_code_url = f"{self.base_url}/{tenant}/applications/{application}/files/{object_id}?start-line={start_line}&end-line={end_line}"
        object_code_response = requests.get(object_code_url, params=self.params, verify=False)
        # Check if the object code was fetched successfully
        if object_code_response.status_code == 200:
            object_code = (object_code_response.text)  # Get object code
        else:
            object_code = ""
            self.app_logger.log_error("get_source", f"Failed to fetch {object_type} {object_id} code using {object_code_url}. Status code: {object_code_response.status_code}", request_id)
        return object_code

    def get_file(self, object_type, tenant, application, file_id, request_id):
        object_code_url = f"{self.base_url}/{tenant}/applications/{application}/files/{file_id}"
        object_code_response = requests.get(object_code_url, params=self.params, verify=False)
        # Check if the object code was fetched successfully
        if object_code_response.status_code == 200:
            object_code = (object_code_response.text)  # Get object code
        else:
            object_code = ""
            self.app_logger.log_error("get_file", f"Failed to fetch {object_type} code using {object_code_url}. Status code: {object_code_response.status_code}", request_id)
        return object_code

    def get_callees(self, tenant, application, object_id):
        object_callees_url = f"{self.base_url}/{tenant}/applications/{application}/objects/{object_id}/callees"
        return requests.get(object_callees_url, params=self.params, verify=False), object_callees_url

    def get_callers(self, tenant, application, object_id):
        object_callers_url = f"{self.base_url}/{tenant}/applications/{application}/objects/{object_id}/callers?select=bookmarks"
        return requests.get(object_callers_url, params=self.params, verify=False), object_callers_url