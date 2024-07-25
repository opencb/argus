import os
import logging
import importlib.util

import yaml
import re
import json
from itertools import product
from datetime import datetime

from dargus.suite import Suite
from dargus.test import Test
from dargus.step import Step
from dargus.validator import Validator
from dargus.validation_result import ValidationResult
from dargus.utils import create_url, replace_random_vars, replace_variables, query


LOGGER = logging.getLogger('argus_logger')


class Argus:
    def __init__(self, argus_config):

        self.config = argus_config

        self.suites = []

        self.suite_ids = []
        self.test_ids = []
        self.step_ids = []

        self.validation_results = []

        # Loading validator
        if 'validator' in self.config and self.config['validator'] is not None:
            LOGGER.debug('Loading custom validator from "{}"'.format(self.config['validator']))
            validator_fpath = self.config['validator']
            validator_fname = os.path.basename(validator_fpath)
            validator_name = validator_fname[:-3] if validator_fname.endswith('.py') else validator_fname
            cls_name = ''.join(x.title() for x in validator_name.split('_'))
            spec = importlib.util.spec_from_file_location(cls_name, validator_fpath)
            foo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(foo)
            validator_class = getattr(foo, cls_name)
            self.validator = validator_class(config=self.config)
        else:
            self.validator = Validator(config=self.config)

        # Logging in
        self.validator.login()

        # Parsing validation files
        self._parse_files(self.config['suiteDir'])  # files must be parsed after validator logs in

    def _select_suites_to_run(self, fpaths):
        selected_suites = []
        for fpath in fpaths:
            # Getting suite ID (basename without last file extension)
            suite_id = '.'.join(os.path.basename(fpath).split('.')[:-1])

            # Checking if duplicated ID
            if suite_id in self.suite_ids:
                raise ValueError('Duplicated suite ID "{}"'.format(suite_id))
            self.suite_ids.append(suite_id)

            # Filtering suites to run with regex support
            if self.config['suites']:
                for s in self.config['suites']:
                    match = re.findall('^' + s + '$', suite_id)
                    if match and match[0] == suite_id:
                        selected_suites.append({'id': suite_id, 'fpath': fpath})
            else:
                selected_suites.append({'id': suite_id, 'fpath': fpath})

        return selected_suites

    def _parse_files(self, suite_dir):
        # Getting all yml files from suite folder
        fpaths = [os.path.join(suite_dir, file)
                  for file in os.listdir(suite_dir)
                  if os.path.isfile(os.path.join(suite_dir, file)) and
                  file.endswith('.yml')]

        # Filtering suites to run
        selected_suites = self._select_suites_to_run(fpaths)

        # Parsing suite file
        for selected_suite in selected_suites:
            suite_id, suite_fpath = selected_suite['id'], selected_suite['fpath']
            LOGGER.debug('Parsing file "{}"'.format(suite_fpath))
            with open(suite_fpath, 'r') as suite_fhand:
                # Replacing RANDOM template functions
                replace_random_vars(suite_fhand.readlines())
                suite_fhand.seek(0)

                # Loading YAML
                try:
                    suite_content = yaml.safe_load(suite_fhand)
                except yaml.parser.ParserError as e:
                    msg = 'Skipping file "{}". Unable to parse YML file. {}.'
                    LOGGER.error(msg.format(suite_fpath, ' '.join(str(e).replace('\n', ' ').split()).capitalize()))
                    continue

            suite = self._parse_suite(suite_id, suite_content)
            if suite is not None:
                self.suites.append(suite)

    def _parse_suite(self, suite_id, suite):
        # Getting base URL
        if suite.get('baseUrl') is None and 'baseUrl' in self.config:
            suite['baseUrl'] = self.config['baseUrl']
        base_url = suite.get('baseUrl')

        # Getting suite output dir
        output_dir = suite.get('outputDir') or os.path.join(self.config['outputDir'], suite_id)

        # Getting suite parameters
        name = suite.get('name') or suite_id
        description = suite.get('description')
        suite_variables = suite.get('variables') or {}

        # Getting tests
        tests = list(filter(None, [self._parse_test(test, suite_variables) for test in suite.get('tests')]))

        # Creating suite
        suite = Suite(id_=suite_id, name=name, description=description, base_url=base_url, variables=suite_variables,
                      tests=tests, output_dir=output_dir)

        return suite

    def _parse_test(self, test, suite_variables):
        # Getting test ID
        id_ = test.get('id')
        if id_ is None:
            raise ValueError('Field "id" is required for each test')
        if id_ in self.test_ids:
            raise ValueError('Duplicated test ID "{}"'.format(id_))
        self.test_ids.append(id_)

        description = test.get('description')
        test_variables = test.get('variables') or {}
        tags = test.get('tags').split(',') if test.get('tags') else None
        path = test.get('path')
        method = test.get('method')
        async_ = test.get('async')

        # Run specific tags if defined
        if self.config['tags']:
            if tags is None or (not set(tags).intersection(set(self.config['tags']))):
                return None

        # Filtering tests to run
        if 'validation' in self.config and self.config['validation'] is not None:
            validation = self.config['validation']
            if 'ignore_async' in validation:
                if async_ in validation['ignore_async']:
                    return None
            if 'ignore_method' in self.config['validation']:
                if method in validation['ignore_method']:
                    return None
            if 'ignore_tag' in self.config['validation']:
                if set(tags).intersection(set(validation['ignore_tag'])):
                    return None

        # Getting test headers
        headers = {}
        if 'headers' in self.config:
            headers.update(self.config['headers'])
        if test.get('headers'):
            headers.update(test.get('headers'))

        steps = []
        for step in test.get('steps'):
            steps += list(filter(None, self._parse_step(step, suite_variables, test_variables)))

        test = Test(id_=id_, description=description, variables=test_variables, tags=tags, path=path, method=method,
                    headers=headers, async_=async_, steps=steps)
        return test

    @staticmethod
    def _parse_matrix_params(matrix_params):
        keys, values = list(matrix_params.keys()), list(matrix_params.values())
        value_product = list(product(*values))
        matrix_params = [
            dict(j) for j in [list(zip(keys, i)) for i in value_product]
        ]
        return matrix_params

    @staticmethod
    def _merge_params(step_id, query_params, matrix_params_list):
        query_params_list = []
        query_params = query_params or {}
        for matrix_params in matrix_params_list:
            new_query_params = query_params.copy()

            duplicated = list(set(matrix_params.keys()) &
                              set(new_query_params.keys()))
            if duplicated:
                msg = '[Step ID: "{}"] Some queryMatrixParams are already' \
                      ' defined in queryParams ("{}")'
                raise ValueError(
                    msg.format(step_id, '";"'.join(duplicated)))

            new_query_params.update(matrix_params)
            query_params_list.append(new_query_params)
        return query_params_list

    def _parse_body(self, step_id, body_params, body_matrix_params, body_file):
        if (body_params is not None or body_matrix_params is not None) and body_file is not None:
            msg = '[Step ID: "{}"] "bodyParams" and "bodyMatrixParams" are not compatible with "bodyFile"'
            raise ValueError(msg)

        body_params_list = [None]
        if body_params is not None:
            body_params_list = [body_params]

        # Parsing body matrix params
        if body_matrix_params is not None:
            matrix_body_params_list = self._parse_matrix_params(body_matrix_params)
            body_params_list = self._merge_params(step_id, body_params, matrix_body_params_list)

        # Parsing body file
        if body_file is not None:
            if not body_file.endswith('.json'):
                msg = '[Step ID: "{}"] Only JSON files (.json) are supported for "bodyFile" param'
                raise IOError(msg.format(step_id))
            body_fhand = open(body_file, 'r')
            body_params_list = [json.loads(body_fhand.read())]

        return body_params_list

    def _parse_step(self, step, suite_variables, test_variables):
        # Getting step ID
        id_ = step.get('id')
        if id_ is None:
            raise ValueError('Field "id" is required for each step')
        if id_ in self.step_ids:
            raise ValueError('Duplicated step ID "{}"'.format(id_))
        self.step_ids.append(id_)

        description = step.get('description')
        step_variables = step.get('variables') or {}
        path_params = step.get('pathParams')
        query_params = step.get('queryParams')
        query_matrix_params = step.get('queryMatrixParams')
        body_params = step.get('bodyParams')
        body_matrix_params = step.get('bodyMatrixParams')
        body_file = step.get('bodyFile')
        validation = step.get('validation')

        # Get variables
        variables = self.config['variables'].copy()
        variables.update(suite_variables)
        variables.update(test_variables)
        variables.update(step_variables)

        # Parsing matrix params
        if query_matrix_params is not None:
            query_matrix_params_list = self._parse_matrix_params(query_matrix_params)
            query_params_list = self._merge_params(id_, query_params, query_matrix_params_list)
        else:
            query_params_list = [query_params]

        # Adding default queryParams
        if 'queryParams' in self.config and self.config['queryParams'] is not None:
            default_params = self.config['queryParams']
            for query_params in query_params_list:
                for key in default_params:
                    if key not in query_params:
                        query_params[key] = default_params[key]

        # Parsing body params
        if variables:
            body_file = replace_variables(body_file, variables)
        body_params_list = self._parse_body(id_, body_params, body_matrix_params, body_file)

        # Replacing variables
        if variables:
            path_params = replace_variables(path_params, variables)
            query_params_list = replace_variables(query_params_list, variables)
            body_params_list = replace_variables(body_params_list, variables)
            validation = replace_variables(validation, variables)

        # Cartesian product between query and body params
        step_params = [i for i in product(query_params_list, body_params_list)]

        # Generating ID list
        id_list = [
            '{}-{}'.format(id_, i+1) for i in range(len(step_params))
        ] if len(step_params) > 1 else [id_]

        # Creating steps
        steps = [
            Step(id_=id_, description=description, variables=step_variables, path_params=path_params,
                 query_params=step_params[i][0], body_params=step_params[i][1], validation=validation)
            for i, id_ in enumerate(id_list)
        ]

        return list(filter(None, steps))

    def _get_validation_results(self, response, current, url, headers, job_id=None):
        # Validating response
        validation = None
        if not current.tests[0].async_:  # Non-asynchronous queries
            response_is_valid, events = self.validator.validate_response(response)
            if response_is_valid:
                validation = self.validator.validate(response, current)
            self.validator.run_after_validation(response, current)
        else:  # Asynchronous queries
            response_is_valid, events = self.validator.validate_async_response(response)
            if response_is_valid:
                validation = self.validator.validate(response, current)
            self.validator.run_after_async_validation(response, current)

        # Creating validation result
        vr = ValidationResult(current=current,
                              url=url,
                              response=response,
                              validation=validation,
                              events=events,
                              headers=headers,
                              job_id=job_id)
        self.validation_results.append(vr)

    def _write_output(self, suite):
        """Write validation results in different file formats"""

        # Setting up timestamp for file names
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

        # Writing to JSON file
        out_fpath_json = os.path.join(suite.output_dir, '{}_{}.json'.format(suite.id_, timestamp))
        LOGGER.debug('Writing results to "{}"'.format(out_fpath_json))
        if not self.config['dry_run']:
            out_fhand = open(out_fpath_json, 'w')
            out_fhand.write('\n'.join([json.dumps(vr.to_json()) for vr in self.validation_results]) + '\n')
            out_fhand.close()

        # Writing to HTML file
        out_fpath_html = os.path.join(suite.output_dir, '{}_{}.html'.format(suite.id_, timestamp))
        LOGGER.debug('Writing results to "{}"'.format(out_fpath_html))
        if not self.config['dry_run']:
            out_fhand = open(out_fpath_html, 'w')
            out_fhand.write('\n'.join([vr.to_html() for vr in self.validation_results]) + '\n')
            out_fhand.close()

    def execute(self):
        """
        Executes the validation of every suite-test-step:
            - Create URL and other querying parameters
            - Query the webservice
            - Validate the response
            - Write output files with validation results
        """

        for suite in self.suites:
            os.makedirs(suite.output_dir, exist_ok=True)  # Setting up output directory for the suite
            current = suite
            for test in suite.tests:
                current.tests = [test]
                for step in test.steps:
                    current.tests[0].steps = [step]

                    # Getting query parameters
                    LOGGER.debug('Creating URL: Suite "{}"; Test "{}"; Step "{}"'.format(suite.id_, test.id_, step.id_))
                    url = create_url(url='/'.join([current.base_url.strip('/'),
                                                   current.tests[0].path.strip('/')]),
                                     path_params=current.tests[0].steps[0].path_params,
                                     query_params=current.tests[0].steps[0].query_params)
                    current.tests[0].steps[0].url = url
                    method = current.tests[0].method
                    headers = current.tests[0].headers
                    body = current.tests[0].steps[0].body_params

                    # Querying current suite-test-step
                    LOGGER.debug('Querying: Suite "{}"; Test "{}"; Step "{}"'.format(suite.id_, test.id_, step.id_))
                    LOGGER.debug('Query: {} {} {}'.format(method, url, body))

                    # Stop if dry-run
                    if self.config['dry_run']:
                        continue

                    # Querying
                    job_id = None
                    if not current.tests[0].async_:  # Non-asynchronous queries
                        response = query(url=url, method=method, headers=headers, body=body)
                    else:  # Asynchronous queries
                        response, job_id = self.validator.get_async_response_for_validation(
                            response=query(url=url, method=method, headers=headers, body=body),
                            current=current
                        )

                    # Validating results
                    LOGGER.debug('Validating: Suite "{}"; Test "{}"; Step "{}"'.format(suite.id_, test.id_, step.id_))
                    self._get_validation_results(response, current, url, headers, job_id)

            # Writing output
            self._write_output(suite)
