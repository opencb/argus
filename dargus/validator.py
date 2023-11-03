import re

from dargus.utils import get_item_from_json, dot2python, num_compare
from dargus.argus_exceptions import ValidationError


class Validator:
    def __init__(self, config, auth_token=None):
        self._config = config
        self._rest_response = None
        self._rest_response_json = None
        self._current = None
        self._step = None
        self._stored_values = {}
        self._auth_token = auth_token

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
        field_value = self.get_item(field)
        return num_compare(field_value, value, operator)

    def match(self, field, regex):
        field_value = self.get_item(field)
        return any(re.findall(regex, field_value))

    def empty(self, field):
        try:
            field_value = self.get_item(field)
        except (TypeError, KeyError, IndexError):
            return False
        return not field_value

    def list_length(self, field, value, operator='eq'):
        field_value = self.get_item(field)
        return num_compare(len(field_value), value, operator)

    def list_contains(self, field, value, expected=True):
        field_value = self.get_item(field)
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

    def list_apply(self, field, value, all_=False):
        field_value = self.get_item(field)
        lambda_function = self._to_python_lambda(value)
        res = [eval(lambda_function, {'self': self})(i) for i in field_value]
        if all_:
            return all(res)
        else:
            return any(res)

    def list_equals(self, field, value, is_sorted=True):
        field_value = self.get_item(field)
        if len(field) != len(value):
            return False
        if is_sorted:
            return field_value == value
        else:
            return sorted(field_value) == sorted(value)

    def list_intersect(self, field, value, all_intersect=True):
        field_value = self.get_item(field)
        intersection = [item for item in list(value) if item in list(field_value)]
        if intersection == value or ((not all_intersect) and len(intersection) > 0):
            return True
        return False

    def list_sorted(self, field, reverse=False):
        field_value = self.get_item(field)
        return field_value == sorted(field_value, reverse=reverse)

    def dict_equals(self, field, value):
        field_value = self.get_item(field)
        if len(field) != len(value):
            return False
        else:
            return field_value == value

    def store(self, field, variable_name):
        field_value = self.get_item(field)
        self._stored_values[variable_name] = field_value
        return True

    def _is_defined(self, method_name):
        return method_name in dir(self)

    def _validate_results(self, methods, exclude=None):
        results = []
        for method in methods:
            method_parts = re.search(r'^(.+?)\((.*)\)$', method)
            name = method_parts.group(1)
            args = method_parts.group(2)

            if name in exclude:
                continue

            if not self._is_defined(name):
                msg = 'Validation method "{}" not defined'
                raise AttributeError(msg.format(name))

            result = eval('self.{}({})'.format(name, args))

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
        min_time = min(0, abs(step_time - time_deviation))
        if not min_time < request_time < max_time:
            return False
        return True

    def validate_headers(self, step_headers, exclude=None):
        for key in step_headers.keys():
            if key not in exclude and (
                    key not in self._rest_response.headers.keys() or
                    self._rest_response.headers[key] != step_headers[key]
            ):
                return False
        return True

    def validate_status_code(self, step_status_code):
        if not step_status_code == self._rest_response.status_code:
            return False
        return True

    def validate(self, response, current):
        self._rest_response = response
        self._rest_response_json = response.json()
        self._current = current
        self._step = self._current.tests[0].steps[0]
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

    def get_async_response_for_validation(self, response, current, url, method, headers, auth_token):
        return response

    def validate_response(self, response):
        return True, None

    def validate_async_response(self, response):
        return True, None
