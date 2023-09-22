import os
import sys
import logging
import random
import string

import yaml
import gzip
import re
import json
from itertools import product
from datetime import datetime

from dargus.validator import Validator
from dargus.validation_result import ValidationResult
from dargus.utils import get_item_from_json, create_url
from dargus.commons import query


LOGGER = logging.getLogger('argus_logger')


class _Suite:
    def __init__(self, id_, base_url=None, tests=None):
        self.id_ = id_
        self.base_url = base_url
        self.tests = tests

    def __str__(self):
        return str(self.__dict__)


class _Test:
    def __init__(self, id_, tags=None, path=None, method=None, async_=None,
                 steps=None):
        self.id_ = id_
        self.tags = tags
        self.path = path
        self.method = method
        self.async_ = async_
        self.steps = steps

    def __str__(self):
        return str(self.__dict__)


class _Step:
    def __init__(self, id_, path_params=None, query_params=None, body_params=None,
                 validation=None):
        self.id_ = id_
        self.path_params = path_params
        self.query_params = query_params
        self.body_params = body_params
        self.validation = validation

    def __str__(self):
        return str(self.__dict__)


class Argus:
    def __init__(self, suite_dir, argus_config, output_prefix=None, output_dir=None):
        self.test_folder = os.path.realpath(os.path.expanduser(suite_dir))

        self.config = argus_config

        # Setting up output directory
        if output_dir is None:
            self.out_fpath = suite_dir
        else:
            out_fpath = os.path.realpath(os.path.expanduser(output_dir))
            os.makedirs(out_fpath, exist_ok=True)
            self.out_fpath = out_fpath

        # Setting up output file names
        if output_prefix is None:
            self.out_prefix = 'argus_out_' + datetime.now().strftime('%Y%m%d%H%M%S')
        else:
            self.out_prefix = output_prefix

        self.suites = []

        self.suite_ids = []
        self.test_ids = []
        self.step_ids = []

        self.current = None
        self.test = None
        self.step = None
        self.token = None
        self.url = None
        self.headers = {}
        self.response = None
        self.async_jobs = []
        self.validation_results = []

        self._parse_files(self.test_folder)
        self._generate_headers()
        self._generate_token()

        # Loading validator
        if 'validator' in self.config and self.config['validator'] is not None:
            LOGGER.debug('Loading custom validator from "{}"'.format(self.config['validator']))
            import importlib.util
            val_path = self.config['validator']
            val_fname = os.path.basename(val_path)
            val_name = val_fname[:-3] if val_fname.endswith('.py') else val_fname
            cls_name = ''.join(x.title() for x in val_name.split('_'))
            spec = importlib.util.spec_from_file_location(cls_name, val_path)
            foo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(foo)
            validator_class = getattr(foo, cls_name)
            self.validator = validator_class(
                config=self.config, token=self.token
            )
        else:
            self.validator = Validator(
                config=self.config, token=self.token
            )

    def _generate_headers(self):
        if 'rest' in self.config and self.config['rest'] is not None and self.config['rest']['headers']:
            self.headers = self.config['rest']['headers']

    @staticmethod
    def _login(auth, field):
        url = create_url(auth['url'], auth.get('pathParams'),
                         auth.get('queryParams'))
        LOGGER.debug('Logging in: {} {} {}'.format(auth.get('method'), url, auth.get('bodyParams')))
        response = query(url, method=auth.get('method'), headers=auth.get('headers'), body=auth.get('bodyParams'))
        token = get_item_from_json(response.json(), field)
        return token

    def _generate_token(self):
        if 'authentication' in self.config and self.config['authentication'] is not None:
            auth = self.config['authentication']
            token_func = re.findall(r'^(.+)\((.+)\)$', auth['token'])
            if token_func:
                if token_func[0][0] == 'env':
                    self.token = os.environ[token_func[1]]
                elif token_func[0][0] == 'login':
                    self.token = self._login(auth, token_func[0][1])
            else:
                self.token = auth['token']
            self.headers['Authorization'] = 'Bearer {}'.format(self.token)

    def _parse_files(self, test_folder):
        fpaths = [os.path.join(test_folder, file)
                  for file in os.listdir(test_folder)
                  if os.path.isfile(os.path.join(test_folder, file)) and
                  file.endswith('.yml')]
        for fpath in fpaths:
            LOGGER.debug('Parsing file "{}"'.format(fpath))
            with open(fpath, 'r') as fhand:
                try:
                    suite = yaml.safe_load(fhand)
                except yaml.parser.ParserError as e:
                    msg = 'Skipping file "{}". Unable to parse YML file. {}.'
                    LOGGER.error(msg.format(fpath, ' '.join(str(e).replace('\n', ' ').split()).capitalize()))
                    continue
            suite = self._parse_suite(suite)
            if suite is not None:
                self.suites.append(suite)

    def _parse_suite(self, suite):
        # Getting suite ID
        id_ = suite.get('id')
        if id_ is None:
            raise ValueError('Field "id" is required for each suite')
        if id_ in self.suite_ids:
            raise ValueError('Duplicated suite IDs "{}"'.format(id_))
        self.suite_ids.append(id_)

        # Filtering suites to run
        if 'suites' in self.config and self.config['suites'] is not None:
            if id_ not in self.config['suites']:
                return None

        # Getting base URL
        if suite.get('baseUrl') is None and 'baseUrl' in self.config:
            suite['baseUrl'] = self.config['baseUrl']
        base_url = suite.get('baseUrl')

        tests = list(filter(
            None, [self._parse_test(test) for test in suite.get('tests')]
        ))

        suite = _Suite(id_=id_, base_url=base_url, tests=tests)

        return suite

    def _parse_test(self, test):
        # Getting test ID
        id_ = test.get('id')
        if id_ is None:
            raise ValueError('Field "id" is required for each test')
        if id_ in self.test_ids:
            raise ValueError('Duplicated test ID "{}"'.format(id_))
        self.test_ids.append(id_)

        tags = test.get('tags').split(',') if test.get('tags') else None
        path = test.get('path')
        method = test.get('method')
        async_ = test.get('async')

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

        steps = []
        for step in test.get('steps'):
            steps += list(filter(None, self._parse_step(step)))

        test = _Test(id_=id_, tags=tags, path=path, method=method,
                     async_=async_, steps=steps)
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
            body_params_list = json.loads(body_fhand.read())

        return body_params_list

    @staticmethod
    def replace_template_vars(params):
        for param in params:
            if '${' in params[param]:
                template, func, args = re.findall('.*(\${(.*\((.*)\))}).*', params[param])[0]
                if func.startswith('RANDOM'):
                    n = int(args) if args else 6
                    random_value = ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))
                elif func.startswith('RANDINT'):
                    a, b = map(int, re.sub(re.compile(r'\s+'), '', args).split(','))
                    random_value = str(random.randint(a, b))
                elif func.startswith('RANDCHOICE'):
                    choices = re.sub(re.compile(r'\s+'), '', args).split(',')
                    random_value = random.choice(choices)
                else:
                    raise ValueError('Template function "{}" not supported'.format(template))
                params[param] = params[param].replace(template, random_value)
        return params

    def _parse_step(self, step):
        # Getting step ID
        id_ = step.get('id')
        if id_ is None:
            raise ValueError('Field "id" is required for each step')
        if id_ in self.step_ids:
            raise ValueError('Duplicated step ID "{}"'.format(id_))
        self.step_ids.append(id_)

        path_params = step.get('pathParams')
        query_params = step.get('queryParams')
        query_matrix_params = step.get('queryMatrixParams')
        body_params = step.get('bodyParams')
        body_matrix_params = step.get('bodyMatrixParams')
        body_file = step.get('bodyFile')
        validation = step.get('validation')

        # Parsing matrix params
        if query_matrix_params is not None:
            query_matrix_params_list = self._parse_matrix_params(query_matrix_params)
            query_params_list = self._merge_params(id_, query_params, query_matrix_params_list)
        else:
            query_params_list = [query_params]

        # Adding default queryParams
        if 'rest' in self.config and self.config['rest'] is not None and self.config['rest']['queryParams']:
            default_params = self.config['rest']['queryParams']
            for query_params in query_params_list:
                for key in default_params:
                    if key not in query_params:
                        query_params[key] = default_params[key]

        # Parsing body params
        body_params_list = self._parse_body(id_, body_params, body_matrix_params, body_file)

        # Replace template variables
        path_params = self.replace_template_vars(path_params)
        query_params_list = [self.replace_template_vars(params) if params else None for params in query_params_list]
        body_params_list = [self.replace_template_vars(params) if params else None for params in body_params_list]

        # Cartesian product between query and body params
        step_params = [i for i in product(query_params_list, body_params_list)]

        # Generating ID list
        id_list = [
            '{}-{}'.format(id_, i+1) for i in range(len(step_params))
        ] if len(step_params) > 1 else [id_]

        # Creating steps
        steps = [
            _Step(id_=id_, path_params=path_params,
                  query_params=step_params[i][0], body_params=step_params[i][1],
                  validation=validation)
            for i, id_ in enumerate(id_list)
        ]

        return list(filter(None, steps))

    def query_step(self):
        url = '/'.join(s.strip('/') for s in [self.current.base_url,
                                              self.current.tests[0].path])
        self.url = create_url(url, self.current.tests[0].steps[0].path_params,
                              self.current.tests[0].steps[0].query_params)
        LOGGER.debug('Query: {} {} {}'.format(self.current.tests[0].method, self.url,
                                              self.current.tests[0].steps[0].body_params))
        response = query(self.url, method=self.current.tests[0].method, headers=self.headers,
                         body=self.current.tests[0].steps[0].body_params)
        self.response = response

    def execute(self):
        validation_results = []
        for suite in self.suites:
            self.current = suite
            for test in suite.tests:
                self.current.tests = [test]
                for step in test.steps:
                    self.current.tests[0].steps = [step]
                    LOGGER.debug('Querying: Suite "{}"; Test "{}"; Step "{}"'.format(suite.id_, test.id_, step.id_))
                    self.query_step()
                    if not self.current.tests[0].async_:
                        res = self.validator.validate(
                            self.response, self.current
                        )
                        vr = ValidationResult(
                            current=self.current,
                            url=self.url,
                            response=self.response,
                            validation=res,
                            headers=self.headers,
                        )
                        validation_results.append(vr)

                    else:
                        self.async_jobs.append(
                            {
                                'current': self.current,
                                'url': self.url,
                                'headers': self.headers,
                                'response': self.response
                            }
                        )
            if self.async_jobs:
                async_res = self.validator.validate_async(self.async_jobs)
                validation_results += async_res

        # Writing to JSON file
        out_fhand = open(os.path.join(self.out_fpath, self.out_prefix + '.json'), 'w')
        out_fhand.write('\n'.join([json.dumps(vr.to_json()) for vr in validation_results]) + '\n')
        out_fhand.close()

        # Writing to HTML file
        out_fhand = open(os.path.join(self.out_fpath, self.out_prefix + '.html'), 'w')
        out_fhand.write('\n'.join([vr.to_html() for vr in validation_results]) + '\n')
        out_fhand.close()
