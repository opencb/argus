import re

from commons import get_item


class Validator:
    def __init__(self, config=None):
        self.config = self.get_default_config()
        if config is not None:
            self.config.update(config)

        self._rest_response = None
        self._rest_response_json = None
        self._validation = None
        self._async_jobs = []

    @staticmethod
    def get_default_config():
        # TODO
        config = {
            'timeDeviation': 100,
            'asyncRetryTime': 10
        }
        return config

    @property
    def rest_response(self):
        return self._rest_response

    @rest_response.setter
    def rest_response(self, rest_response):
        self._rest_response = rest_response
        self._rest_response_json = rest_response.json()

    @property
    def validation(self):
        return self._validation

    @validation.setter
    def validation(self, validation):
        self._validation = validation

    @property
    def async_jobs(self):
        return self._async_jobs

    @async_jobs.setter
    def async_jobs(self, async_jobs):
        self._async_jobs = async_jobs

    @staticmethod
    def num_compare(a, b, operator):
        a, b = float(a), float(b)
        if operator in ['=', '==', 'eq']:
            return a == b
        elif operator in ['!=', 'ne']:
            return a != b
        elif operator in ['>', 'gt']:
            return a > b
        elif operator in ['>=', 'ge']:
            return a >= b
        elif operator == ['<', 'lt']:
            return a < b
        elif operator == ['<=', 'le']:
            return a <= b

    def compare(self, field, value, operator='eq'):
        field_value = get_item(self._rest_response_json, field)
        return self.num_compare(field_value, value, operator)

    def match(self, field, regex):
        field_value = get_item(self._rest_response_json, field)
        return any(re.findall(regex, field_value))

    def empty(self, field):
        try:
            field_value = get_item(self._rest_response_json, field)
        except (TypeError, KeyError, IndexError):
            return False
        return not field_value

    def list_length(self, field, value, operator='eq'):
        field_value = get_item(self._rest_response_json, field)
        return self.num_compare(len(field_value), value, operator)

    def list_contains(self, field, value, expected=True):
        field_value = get_item(self._rest_response_json, field)
        if expected:
            return value in field_value
        else:
            return value not in field_value

    def list_apply(self, field, value, all_=False):
        field_value = get_item(self._rest_response_json, field)
        if not value.startswith('lambda'):
            value = 'lambda ' + value
        res = [eval(value)(i) for i in field_value]
        if all_:
            return all(res)
        else:
            return any(res)

    def list_equals(self, field, value, is_sorted=True):
        field_value = get_item(self._rest_response_json, field)
        if len(field) != len(value):
            return False
        if is_sorted:
            return field_value == value
        else:
            return sorted(field_value) == sorted(value)

    def list_sorted(self, field, reverse=False):
        field_value = get_item(self._rest_response_json, field)
        return field_value == sorted(field_value, reverse=reverse)

    def dict_equals(self, field, value):
        field_value = get_item(self._rest_response_json, field)
        if len(field) != len(value):
            return False
        else:
            return field_value == value

    def _is_defined(self, method_name):
        return method_name in dir(self)

    def _validate_results(self, methods):
        results = []
        for method in methods:
            method_parts = re.search(r'^(.+)\((.*)\)$', method)
            name = method_parts.group(1)
            args = method_parts.group(2)

            if not self._is_defined(name):
                msg = 'Validation method "{}" not defined'
                raise AttributeError(msg.format(name))

            results.append(
                {'function': method,
                 'result': eval('self.{}({})'.format(name, args))}
            )
        return results

    def validate_time(self, task_time):
        request_time = self._rest_response.elapsed.total_seconds()
        max_time = task_time + task_time*self.time_deviation/100
        min_time = task_time - task_time*self.time_deviation/100
        if not min_time < request_time < max_time:
            return False
        return True

    def validate_headers(self, task_headers):
        for key in task_headers.keys():
            if key not in self.rest_response.headers.keys() or \
                    self.rest_response.headers[key] != task_headers[key]:
                return False
        return True

    def validate_status_code(self, task_status_code):
        if not task_status_code == self.rest_response.status_code:
            return False
        return True

    def validate(self, response, validation):

        self.rest_response = response
        self.validation = validation
        results = []

        # Time
        if 'time' in self.validation and 'time_deviation' in self.config:
            results.append(
                {'function': 'validate_time',
                 'result': self.validate_time(self.validation['time'])}
            )

        # Headers
        if 'headers' in self.validation:
            results.append(
                {'function': 'validate_headers',
                 'result': self.validate_headers(self.validation['headers'])}
            )

        # Status code
        task_status_code = self.validation.get('status_code', 200)
        results.append(
            {'function': 'validate_status_code',
             'result': self.validate_status_code(task_status_code)}
        )

        # Results
        if 'results' in self.validation:
            results = self._validate_results(self.validation['results'])

        return results
