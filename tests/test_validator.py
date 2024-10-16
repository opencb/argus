import unittest
from unittest.mock import Mock, patch
import json
import logging

from dargus.validator import Validator


class TestValidator(unittest.TestCase):
    def setUp(self):
        """Set up a configuration for testing"""
        # Disabling log messages
        logging.disable(logging.CRITICAL)

        # Default configuration
        self.test_config = {
            'validator': '/path/to/custom_validator.py',
            'suiteDir': '/path/to/suite_dir',
            'suites': ['validation-suite'],
            'tags': 'DEMO',
            'inputDir': '/path/to/input_dir',
            'outputDir': '/path/to/output_dir',
            'dry_run': False,
            'variables': {'varName': 'var_value',
                          'INPUT_DIR': '/path/to/input_dir',
                          'OUTPUT_DIR': '/path/to/output_dir'},
            'baseUrl': 'https://mock/url',
            'authentication': {'token': 'login(responses[0].results[0].token)',
                               'url': 'https://mock/url',
                               'headers': {'Accept-Encoding': 'gzip'}, 'method': 'POST',
                               'bodyParams': {'user': 'USER', 'password': 'PASS'}},
            'validation': {'timeDeviation': 5, 'asyncRetryTime': 60, 'ignoreTime': False, 'ignoreHeaders': [],
                           'ignoreResults': [], 'failOnFirst': False}
        }
        
        # Default validator
        self.validator = Validator(config=self.test_config)

    def test_get_item(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'key': 'value'}]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Getting value from JSON using dot notation
        self.assertEqual(self.validator.get_item('responses[0].results[0].key'), 'value')

        # Getting value from stored JSON using dot notation
        self.assertEqual(self.validator.get_item('<stored_key>.responses[0].results[0].key'), 'value')

        # Getting the entire stored JSON
        self.assertEqual(self.validator.get_item('<stored_key>'), {'responses': [{'results': [{'key': 'value'}]}]})

    def test_compare(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'key': '25'}]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Comparing values
        self.assertTrue(self.validator.compare('responses[0].results[0].key', 25, 'eq'))
        self.assertTrue(self.validator.compare('responses[0].results[0].key', 1000, 'ne'))
        self.assertTrue(self.validator.compare('responses[0].results[0].key', 20, 'gt'))
        self.assertTrue(self.validator.compare('responses[0].results[0].key', 25, 'ge'))
        self.assertTrue(self.validator.compare('responses[0].results[0].key', 30, 'lt'))
        self.assertTrue(self.validator.compare('responses[0].results[0].key', 25, 'le'))
        self.assertFalse(self.validator.compare('responses[0].results[0].key', 1000, 'eq'))
        self.assertFalse(self.validator.compare('responses[0].results[0].key', 25, 'ne'))
        self.assertFalse(self.validator.compare('responses[0].results[0].key', 25, 'gt'))
        self.assertFalse(self.validator.compare('responses[0].results[0].key', 30, 'ge'))
        self.assertFalse(self.validator.compare('responses[0].results[0].key', 25, 'lt'))
        self.assertFalse(self.validator.compare('responses[0].results[0].key', 20, 'le'))

        # Comparing stored values
        self.assertTrue(self.validator.compare('<stored_key>.responses[0].results[0].key', 25, 'eq'))
        self.assertFalse(self.validator.compare('<stored_key>.responses[0].results[0].key', 1000, 'eq'))

    def test_match(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'key': 'abc_123'}]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Comparing entire strings
        self.assertTrue(self.validator.match('responses[0].results[0].key', 'abc_123'))
        self.assertFalse(self.validator.match('responses[0].results[0].key', 'xyz_789'))

        # Comparing using regex
        self.assertTrue(self.validator.match('responses[0].results[0].key', '123'))
        self.assertFalse(self.validator.match('responses[0].results[0].key', 'xyz'))
        self.assertTrue(self.validator.match('responses[0].results[0].key', '^[a-z]+_[0-9]+$'))
        self.assertFalse(self.validator.match('responses[0].results[0].key', '^[a-z]+-[0-9]+$'))

        # Comparing stored values
        self.assertTrue(self.validator.match('<stored_key>.responses[0].results[0].key', 'abc_123'))
        self.assertFalse(self.validator.match('<stored_key>.responses[0].results[0].key', 'xyz_789'))

    def test_is_not_empty(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'k1': 'value', 'k2': '', 'k3': [],
                                                                          'k4': ['']}]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Checking if a field is not empty
        self.assertTrue(self.validator.is_not_empty('responses[0].results[0].k1'))
        self.assertFalse(self.validator.is_not_empty('responses[0].results[0].k2'))
        self.assertFalse(self.validator.is_not_empty('responses[0].results[0].k3'))
        self.assertTrue(self.validator.is_not_empty('responses[0].results[0].k4'))

        # Checking stored values
        self.assertTrue(self.validator.is_not_empty('<stored_key>.responses[0].results[0].k1'))
        self.assertFalse(self.validator.is_not_empty('<stored_key>.responses[0].results[0].k2'))

    def test_is_empty(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'k1': 'value', 'k2': '', 'k3': [],
                                                                          'k4': ['']}]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Checking if a field is empty
        self.assertFalse(self.validator.is_empty('responses[0].results[0].k1'))
        self.assertTrue(self.validator.is_empty('responses[0].results[0].k2'))
        self.assertTrue(self.validator.is_empty('responses[0].results[0].k3'))
        self.assertFalse(self.validator.is_empty('responses[0].results[0].k4'))

        # Checking stored values
        self.assertFalse(self.validator.is_empty('<stored_key>.responses[0].results[0].k1'))
        self.assertTrue(self.validator.is_empty('<stored_key>.responses[0].results[0].k2'))

    def test_string_to_type(self):
        self.assertTrue(self.validator._string_to_type('abc'), 'abc')
        self.assertTrue(self.validator._string_to_type('1'), 1)
        self.assertTrue(self.validator._string_to_type('1.05'), 1.05)
        self.assertTrue(self.validator._string_to_type('[1, 2, 3]'), [1, 2, 3])
        self.assertTrue(self.validator._string_to_type('{"k1": "v1", "k2": [1, 2, 3]}'), {'k1': 'v1', 'k2': [1, 2, 3]})

    def test_list_length(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'k1': [1, 2, 3], 'k2': []}]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Comparing list lengths
        self.assertTrue(self.validator.list_length('responses[0].results[0].k1', 3, 'eq'))
        self.assertTrue(self.validator.list_length('responses[0].results[0].k1', '3', 'eq'))
        self.assertTrue(self.validator.list_length('responses[0].results[0].k2', '0', 'eq'))
        self.assertFalse(self.validator.list_length('responses[0].results[0].k1', '3', 'ne'))

        # Comparing stored list lengths
        self.assertTrue(self.validator.list_length('<stored_key>.responses[0].results[0].k1', '3', 'eq'))
        self.assertTrue(self.validator.list_length('<stored_key>.responses[0].results[0].k2', '0', 'eq'))
        self.assertFalse(self.validator.list_length('<stored_key>.responses[0].results[0].k1', '3', 'ne'))

    def test_list_contains(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'k1': [1, 2, 3], 'k2': ['A']}]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Checking list elements
        self.assertTrue(self.validator.list_contains('responses[0].results[0].k1', 1))
        self.assertTrue(self.validator.list_contains('responses[0].results[0].k1', '1'))
        self.assertTrue(self.validator.list_contains('responses[0].results[0].k2', 'A'))
        self.assertTrue(self.validator.list_contains('responses[0].results[0].k2', '0', expected=False))
        self.assertTrue(self.validator.list_contains('responses[0].results[0].k2', '0', expected='False'))
        self.assertFalse(self.validator.list_contains('responses[0].results[0].k2', '3'))

        # Checking stored list elements
        self.assertTrue(self.validator.list_contains('<stored_key>.responses[0].results[0].k1', '1'))
        self.assertTrue(self.validator.list_contains('<stored_key>.responses[0].results[0].k2', '0', expected=False))
        self.assertTrue(self.validator.list_contains('<stored_key>.responses[0].results[0].k2', '0', expected='False'))
        self.assertFalse(self.validator.list_contains('<stored_key>.responses[0].results[0].k2', '3'))

    def test_to_python_lambda(self):
        # Convert java lambda and not dot notation to python lambda and python notation
        self.assertEqual(
            self.validator._to_python_lambda('v -> int(v.evidences[0].attributes.exomiser.RANK) >= 0'),
            'lambda v : int(v["evidences"][0]["attributes"]["exomiser"]["RANK"]) >= 0'
        )

    def test_list_apply(self):
        self.validator._rest_response_json = {'responses': [{'results': [
            {'k1': [1, 2, 3],
             'k2': [1, 'two', 3.00],
             'k3': [{'k3_1': [2, "3", 20.567764]}]}
        ]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Applying validation to each element in a list
        self.assertTrue(self.validator.list_apply('responses[0].results[0].k1', 'v -> type(v) == int'))
        self.assertFalse(self.validator.list_apply('responses[0].results[0].k2', 'v -> type(v) == int'))
        self.assertTrue(self.validator.list_apply('responses[0].results[0].k2', 'v -> type(v) == int', all_=False))
        self.assertTrue(self.validator.list_apply('responses[0].results[0].k2', 'v -> type(v) == int', all_='False'))
        self.assertTrue(self.validator.list_apply('responses[0].results[0].k3', "v -> int(v.k3_1[0]) <= 10"))
        self.assertTrue(self.validator.list_apply('responses[0].results[0].k3', "v -> int(v.k3_1[1]) <= 10"))
        self.assertFalse(self.validator.list_apply('responses[0].results[0].k3', "v -> int(v.k3_1[2]) <= 10"))

        # Applying validation to each element in a stored list
        self.assertTrue(self.validator.list_apply('<stored_key>.responses[0].results[0].k1', 'v -> type(v) == int'))
        self.assertFalse(self.validator.list_apply('<stored_key>.responses[0].results[0].k2', 'v -> type(v) == int'))

    def test_list_equals(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'k1': [1, 2, 3], 'k2': [2, 3]}]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Comparing list elements
        self.assertTrue(self.validator.list_equals('responses[0].results[0].k1', [1, 2, 3]))
        self.assertTrue(self.validator.list_equals('responses[0].results[0].k1', '[1, 2, 3]'))
        self.assertFalse(self.validator.list_equals('responses[0].results[0].k1', '[2, 1, 3]'))
        self.assertTrue(self.validator.list_equals('responses[0].results[0].k1', '[2, 1, 3]', is_sorted=False))
        self.assertTrue(self.validator.list_equals('responses[0].results[0].k1', '[2, 1, 3]', is_sorted='False'))
        self.assertFalse(self.validator.list_equals('responses[0].results[0].k2', '[2, 3, 4]'))
        self.assertFalse(self.validator.list_equals('responses[0].results[0].k2', '[2]'))

        # Comparing stored list elements
        self.assertTrue(self.validator.list_equals('<stored_key>.responses[0].results[0].k1', '[1, 2, 3]'))
        self.assertFalse(self.validator.list_equals('<stored_key>.responses[0].results[0].k1', '[2, 1, 3]'))
        self.assertTrue(self.validator.list_equals('<stored_key>.responses[0].results[0].k1', '[2, 1, 3]',
                                                   is_sorted=False))

    def test_list_intersect(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'k1': [1, 2, 3]}]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Intersecting lists
        self.assertTrue(self.validator.list_intersect('responses[0].results[0].k1', [1, 2]))
        self.assertTrue(self.validator.list_intersect('responses[0].results[0].k1', '[1, 2]'))
        self.assertFalse(self.validator.list_intersect('responses[0].results[0].k1', '[8, 9]'))
        self.assertTrue(self.validator.list_intersect('responses[0].results[0].k1', '[1]'))
        self.assertTrue(self.validator.list_intersect('responses[0].results[0].k1', '["a", 2]', all_intersect=False))
        self.assertTrue(self.validator.list_intersect('responses[0].results[0].k1', '["a", 2]', all_intersect='False'))

        # Intersecting stored lists
        self.assertTrue(self.validator.list_intersect('<stored_key>.responses[0].results[0].k1', '[1, 2]'))
        self.assertFalse(self.validator.list_intersect('<stored_key>.responses[0].results[0].k1', '[8, 9]'))

    def test_list_sorted(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'k1': [1, 2, 3], 'k2': [3, 2, 1]}]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Checking list sorting
        self.assertTrue(self.validator.list_sorted('responses[0].results[0].k1'))
        self.assertFalse(self.validator.list_sorted('responses[0].results[0].k2'))
        self.assertTrue(self.validator.list_sorted('responses[0].results[0].k2', reverse=True))
        self.assertTrue(self.validator.list_sorted('responses[0].results[0].k2', reverse='True'))

        # Checking stored list sorting
        self.assertTrue(self.validator.list_sorted('<stored_key>.responses[0].results[0].k1'))
        self.assertTrue(self.validator.list_sorted('<stored_key>.responses[0].results[0].k2', reverse=True))

    def test_dict_equals(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'k1': [1, 2, 3]}]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Comparing dicts
        self.assertTrue(self.validator.dict_equals('responses[0].results[0]', '{"k1": [1, 2, 3]}'))
        self.assertFalse(self.validator.dict_equals('responses[0].results[0]', '{"k1": [1, "X", 3]}'))
        self.assertFalse(self.validator.dict_equals('<stored_key>.responses[0].results[0]', 'not_a_dict'))

        # Comparing stored dicts
        self.assertTrue(self.validator.dict_equals('<stored_key>.responses[0].results[0]', '{"k1": [1, 2, 3]}'))
        self.assertFalse(self.validator.dict_equals('<stored_key>.responses[0].results[0]', '{"k1": [1, "X", 3]}'))

    def test_store(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'k1': [1, 2, 3]}]}]}
        self.validator._stored_values = {'stored_key': self.validator._rest_response_json}

        # Storing a value under a particular variable name
        self.validator.store('responses[0]', '$variable_name')
        self.assertIn('$variable_name', self.validator._stored_values)
        self.assertNotIn('$not_a_variable_name', self.validator._stored_values)
        self.assertEqual(self.validator._stored_values['$variable_name'],
                         self.validator._rest_response_json['responses'][0])

    def test_validate_results(self):
        self.validator._rest_response_json = {'responses': [{'results': [{'k1': '25', 'k2': 'abc_123'}]}]}
        methods = ["compare('responses[0].results[0].k1', '25')", "match('responses[0].results[0].k2', 'abc_123')"]
        expected_results = [{'function': "compare('responses[0].results[0].k1', '25')", 'result': True},
                            {'function': "match('responses[0].results[0].k2', 'abc_123')", 'result': True}]

        self.assertEqual(self.validator._validate_results(methods), expected_results)
        self.assertEqual(self.validator._validate_results(methods, exclude='compare'), [expected_results[1]])
        self.assertEqual(self.validator._validate_results(methods, exclude=['match', 'compare']), [])

    def test_validate_time(self):
        # Mocking rest response time
        self.validator._rest_response = Mock()
        self.validator._rest_response.elapsed = Mock()

        # Validation time is set as 10, so the allowed time bracket is [5, 15] (timeDeviation == 5)
        self.validator._rest_response.elapsed.total_seconds.return_value = 4  # Rest response time
        self.assertFalse(self.validator.validate_time(10))
        self.validator._rest_response.elapsed.total_seconds.return_value = 5  # Rest response time
        self.assertTrue(self.validator.validate_time(10))
        self.validator._rest_response.elapsed.total_seconds.return_value = 10  # Rest response time
        self.assertTrue(self.validator.validate_time(10))
        self.validator._rest_response.elapsed.total_seconds.return_value = 15  # Rest response time
        self.assertTrue(self.validator.validate_time(10))
        self.validator._rest_response.elapsed.total_seconds.return_value = 16  # Rest response time
        self.assertFalse(self.validator.validate_time(10))

    def test_validate_headers(self):
        # Mocking rest response headers
        self.validator._rest_response = Mock()

        # Validating headers
        self.validator._rest_response.headers = {'Accept-Encoding': 'gzip',
                                                 'Accept-Language': 'en'}    # Rest response headers
        self.assertTrue(self.validator.validate_headers({'Accept-Encoding': 'gzip'}))
        self.assertTrue(self.validator.validate_headers({'Accept-Language': 'en'}))
        self.assertFalse(self.validator.validate_headers({'Accept-Encoding': 'deflate'}))
        self.assertFalse(self.validator.validate_headers({'Accept-Encoding': 'deflate', 'Connection': 'keep-alive'}))

        self.validator._rest_response.headers = {'Connection': 'keep-alive'}  # Rest response headers
        self.assertFalse(self.validator.validate_headers({'Accept-Encoding': 'gzip'}))
        self.assertTrue(self.validator.validate_headers({'Accept-Encoding': 'gzip'}, exclude=['Accept-Encoding']))
        self.assertTrue(self.validator.validate_headers({'Accept-Encoding': 'gzip', 'Connection': 'keep-alive'},
                                                        exclude=['Accept-Encoding']))
        self.assertFalse(self.validator.validate_headers({'Accept-Encoding': 'gzip', 'Connection': 'keep-alive'},
                                                         exclude=['Connection']))

    def test_validate_status_code(self):
        # Mocking rest response headers
        self.validator._rest_response = Mock()

        # Validating status code
        self.validator._rest_response.status_code = 200
        self.assertTrue(self.validator.validate_status_code(200))
        self.assertFalse(self.validator.validate_status_code(404))








