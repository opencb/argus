import re
from datetime import datetime
from dargus.utils import json_to_html, get_argus_version


class ValidationResult:
    def __init__(self, current, url, response, validation, events=None, headers=None):
        self.suite_id = current.id_
        self.test_id = current.tests[0].id_
        self.step_id = current.tests[0].steps[0].id_
        self.url = url
        self.validation = validation
        self.headers = self.get_headers(headers)
        self.tags = current.tests[0].tags
        self.method = current.tests[0].method
        self.async_ = current.tests[0].async_
        self.time = response.elapsed.total_seconds()
        self.params = current.tests[0].steps[0].query_params
        self.status_code = response.status_code
        self.status = self.get_status(validation)
        self.events = events
        self.argus_version = get_argus_version()
        self.timestamp = int(datetime.now().strftime('%Y%m%d%H%M%S'))

        self.format_validation()

    @staticmethod
    def get_headers(headers):
        new_headers = None
        if headers is not None and 'Authorization' in headers:
            new_headers = headers.copy()
            new_headers['Authorization'] = 'REDACTED'
        return new_headers

    @staticmethod
    def get_status(validation):
        validation_results = [v['result'] for v in validation]
        if validation_results:
            status = all([v['result'] for v in validation])
        else:
            status = False
        return 'PASS' if status is True else 'FAIL'

    def format_validation(self):
        for v in self.validation:
            # Converting boolean values
            v['result'] = 'PASS' if v['result'] else 'FAIL'

            # Splitting function name and params
            validation_function_parts = re.search(r'^(.+?)\((.*)\)$', v['function'])
            if validation_function_parts:
                v['function'] = validation_function_parts.group(1)
                v['params'] = validation_function_parts.group(2)
            else:
                v['params'] = None

    def to_json(self):
        return self.__dict__

    def to_html(self):
        return json_to_html(self.__dict__)
