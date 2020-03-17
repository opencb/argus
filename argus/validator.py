import re


class ValidationResult:
    def __init__(self, test_id, task_id, url=None, tags=None, method=None,
                 async_=None, time=None, params=None, headers=None,
                 status_code=None, num_results=None, num_errors=None,
                 errors=None, pass_=None):
        self.test_id = test_id
        self.task_id = task_id
        self.url = url
        self.headers = headers
        self.tags = tags
        self.method = method
        self.async_ = async_
        self.time = time
        self.params = params
        self.status_code = status_code
        self.num_results = num_results
        self.num_errors = num_errors
        self.errors = errors
        self.pass_ = pass_

    def to_json(self):
        return self.__dict__


class Validator:
    def __init__(self, rest_response=None, validation=None,
                 time_deviation=None):
        self._rest_response = rest_response
        self._validation = validation
        self._time_deviation = time_deviation

        self._rest_response_json = rest_response.json() \
            if rest_response else None


        self.results = []

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
    def time_deviation(self):
        return self._time_deviation

    @time_deviation.setter
    def time_deviation(self, time_deviation):
        self._time_deviation = time_deviation

    @staticmethod
    def _get_item(json_dict, field):
        for item in field.split('.'):
            items = list(filter(None, re.split('\[|\]', item)))
            key, indexes = items[0], map(int, items[1:])
            json_dict = json_dict[key]
            if indexes:
                for i in indexes:
                    json_dict = json_dict[i]
        return json_dict

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
        field_value = self._get_item(self._rest_response_json, field)
        return self.num_compare(field_value, value, operator)

    def match(self, field, regex):
        field_value = self._get_item(self._rest_response_json, field)
        return any(re.findall(regex, field_value))

    def empty(self, field):
        try:
            field_value = self._get_item(self._rest_response_json, field)
        except (TypeError, KeyError, IndexError):
            return False
        return not field_value

    def list_length(self, field, value, operator='eq'):
        field_value = self._get_item(self._rest_response_json, field)
        return self.num_compare(len(field_value), value, operator)

    def list_contains(self, field, value):
        field_value = self._get_item(self._rest_response_json, field)
        if 'lambda ' in value:
            return any([eval(value)(i) for i in field_value])
        return value in field_value

    def list_equals(self, field, value, is_sorted=True):
        field_value = self._get_item(self._rest_response_json, field)
        if len(field) != len(value):
            return False
        if is_sorted:
            return field_value == value
        else:
            return sorted(field_value) == sorted(value)

    def list_sorted(self, field, reverse=False):
        field_value = self._get_item(self._rest_response_json, field)
        return field_value == sorted(field_value, reverse=reverse)

    def dict_equals(self, field, value):
        field_value = self._get_item(self._rest_response_json, field)
        if len(field) != len(value):
            return False
        else:
            return field_value == value

    def _is_defined(self, method_name):
        return method_name in dir(self)

    def _validate_results(self, results):
        for result in results:
            method_parts = re.search('^(.+)\((.*)\)$', result)
            method_name = method_parts.group(1)
            method_args = method_parts.group(2)

            if not self._is_defined(method_name):
                msg = 'Validation method "{}" not defined'
                raise AttributeError(msg.format(method_name))

            print(eval('self.{}({})'.format(method_name, method_args)))

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

    def validate(self):
        print(self._rest_response_json)

        # Time
        task_time = self.validation.get('time')
        if task_time:
            self.validate_time(task_time)

        # Headers
        task_headers = self.validation.get('headers')
        if task_headers:
            self.validate_headers(task_headers)

        # Status code
        task_status_code = self.validation.get('status_code', 200)
        self.validate_status_code(task_status_code)

        # Results
        if 'results' in self.validation:
            self._validate_results(self.validation['results'])
