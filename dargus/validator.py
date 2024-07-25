import re
import json
import logging

from dargus.utils import get_item_from_json, dot2python, num_compare
from dargus.argus_exceptions import ValidationError

LOGGER = logging.getLogger('argus_logger')


class Validator:
    def __init__(self, config):
        self._config = config
        self._rest_response = None
        self._rest_response_json = None
        self.current = None
        self._step = None
        self._stored_values = {}
        self.id_ = None

        self.validation = self.get_default_validation()
        if self._config.get('validation') is not None:
            self.validation.update(config.get('validation'))

    @staticmethod
    def get_default_validation():
        validation = {
            'timeDeviation': 100,
            'asyncRetryTime': 10,
            'ignoreTime': False,
            'ignoreHeaders': [],
            'ignoreResults': [],
            'failOnFirst': False
        }
        return validation

    def get_item(self, field):
        if field.startswith('<'):
            variable_name = field.split('.')[0].lstrip('<').rstrip('>')
            field = '.'.join(field.split('.')[1:])
            field_value = get_item_from_json(self._stored_values[variable_name], field)
        else:
            field_value = get_item_from_json(self._rest_response_json, field)
        return field_value

    def compare(self, field, value, operator='eq'):
        field_value = float(self.get_item(field))
        value = float(value)
        return num_compare(field_value, value, operator)

    def match(self, field, regex):
        field_value = self.get_item(field)
        return any(re.findall(regex, field_value))

    def is_not_empty(self, field):
        field_value = self.get_item(field)
        return bool(field_value)

    def is_empty(self, field):
        field_value = self.get_item(field)
        return not bool(field_value)

    @staticmethod
    def _string_to_type(value):
        # Converting string representation of list/dict to a list/dict
        if type(value) is not str:
            return value
        elif value.isdigit():
            return float(value)
        else:
            try:
                value = json.loads(value)
            except json.decoder.JSONDecodeError:
                return value
        return value

    def list_length(self, field, value, operator='eq'):
        field_value = self.get_item(field)
        return num_compare(len(field_value), value, operator)

    def list_contains(self, field, value, expected=True):
        field_value = self.get_item(field)
        if type(expected) is not bool:
            expected = True if expected.lower() == 'true' else False
        value = self._string_to_type(value)
        if expected:
            return value in field_value
        else:
            return value not in field_value

    @staticmethod
    def _to_python_lambda(value):
        value = value.replace('lambda', '')

        # From dot notation to python notation
        variables = filter(None, re.split('[-+*/=><|! ]', value))
        for v in variables:
            value = value.replace(v, dot2python(v))

        # Internal variables (e.g. "$QUERY_PARAMS")
        value = value.replace('$QUERY_PARAMS', 'self.step.query_params')

        value = 'lambda ' + value.replace('->', ':')
        return value

    def list_apply(self, field, value, all_=True):
        field_value = self.get_item(field)
        if type(all_) is not bool:
            all_ = True if all_.lower() == 'true' else False
        lambda_function = self._to_python_lambda(value)
        res = [eval(lambda_function, {'self': self})(i) for i in field_value]
        if all_:
            return all(res)
        else:
            return any(res)

    def list_equals(self, field, value, is_sorted=True):
        field_value = self.get_item(field)
        value = self._string_to_type(value)
        if type(is_sorted) is not bool:
            is_sorted = True if is_sorted.lower() == 'true' else False
        return field_value == value if is_sorted else sorted(field_value) == sorted(value)

    def list_intersect(self, field, value, all_intersect=True):
        field_value = self.get_item(field)
        value = self._string_to_type(value)
        if type(all_intersect) is not bool:
            all_intersect = True if all_intersect.lower() == 'true' else False
        intersection = [item for item in list(value) if item in list(field_value)]
        if intersection == value or ((not all_intersect) and len(intersection) > 0):
            return True
        return False

    def list_sorted(self, field, reverse=False):
        field_value = self.get_item(field)
        if type(reverse) is not bool:
            reverse = True if reverse.lower() == 'true' else False
        return field_value == sorted(field_value, reverse=reverse)

    def dict_equals(self, field, value):
        field_value = self.get_item(field)
        value = self._string_to_type(value)
        return field_value == value

    def store(self, field, variable_name):
        field_value = self.get_item(field)
        self._stored_values[variable_name] = field_value
        return True

    def _validate_results(self, methods, exclude=None):
        results = []
        for method in methods:
            method_parts = re.search(r'^(.+?)\((.*)\)$', method)
            method_name = method_parts.group(1)
            method_args = method_parts.group(2)

            if exclude and method_name in exclude:
                continue

            if method_name not in dir(self):
                msg = 'Validation method "{}" not defined'
                raise AttributeError(msg.format(method_name))

            result = eval('self.{}({})'.format(method_name, method_args))

            # Raise error if failOnFirst is True
            if self.validation['failOnFirst'] and not result:
                msg = 'Validation function "{}" returned False'
                raise ValidationError(msg.format(method))

            results.append({'function': method, 'result': result})

        # Empty stored values
        self._stored_values = {}

        return results

    def validate_time(self, step_time):
        request_time = self._rest_response.elapsed.total_seconds()
        time_deviation = self.validation['timeDeviation']
        max_time = step_time + time_deviation
        min_time = max(0, abs(step_time - time_deviation))
        if not min_time <= request_time <= max_time:
            return False
        return True

    def validate_headers(self, step_headers, exclude=None):
        for key in step_headers.keys():
            if exclude and key in exclude:
                continue
            if key not in self._rest_response.headers.keys():
                return False
            elif self._rest_response.headers[key] != step_headers[key]:
                return False
        return True

    def validate_status_code(self, step_status_code):
        if not step_status_code == self._rest_response.status_code:
            return False
        return True

    def validate(self, response, current):
        self._rest_response = response
        self._rest_response_json = response.json()
        self.current = current
        self._step = self.current.tests[0].steps[0]
        self.id_ = '.'.join([self.current.id_, self.current.tests[0].id_, self.current.tests[0].steps[0].id_])
        results = []

        # Time
        if self._step.validation and 'time' in self._step.validation and not self.validation['ignoreTime']:
            results.append(
                {'function': 'validate_time',
                 'result': self.validate_time(self._step.validation['time'])}
            )

        # Headers
        if self._step.validation and 'headers' in self._step.validation:
            result_headers = self.validate_headers(
                self._step.validation['headers'],
                exclude=self.validation['ignoreHeaders']
            )
            results.append({'function': 'validate_headers',
                            'result': result_headers})

        # Status code
        step_status_code = 200
        if self._step.validation and 'status_code' in self._step.validation:
            step_status_code = self._step.validation.get('status_code')
        results.append(
            {'function': 'validate_status_code',
             'result': self.validate_status_code(step_status_code)}
        )

        # Results
        if self._step.validation and 'results' in self._step.validation:
            results += self._validate_results(
                self._step.validation['results'],
                exclude=self.validation['ignoreResults']
            )

        return results

    def get_async_response_for_validation(self, response, current):
        return None, None

    def validate_response(self, response):
        return True, None

    def validate_async_response(self, response):
        return True, None

    def run_after_validation(self, response, current):
        pass

    def run_after_async_validation(self, response, current):
        pass

    def login(self):
        pass
