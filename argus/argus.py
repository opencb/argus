import os
import yaml
import gzip
import re
import json
import importlib
from itertools import product
from datetime import datetime

from argus.validator import Validator
from argus.validation_result import ValidationResult
from argus.utils import get_item, create_url, query


class _Suite:
    def __init__(self, id_, base_url=None, tests=None):
        self.id_ = id_
        self.base_url = base_url
        self.tests = tests

    def __str__(self):
        return str(self.__dict__)


class _Test:
    def __init__(self, id_, tags=None, path=None, method=None, async_=None,
                 tasks=None):
        self.id_ = id_
        self.tags = tags
        self.path = path
        self.method = method
        self.async_ = async_
        self.tasks = tasks

    def __str__(self):
        return str(self.__dict__)


class _Task:
    def __init__(self, id_, path_params=None, query_params=None, body=None,
                 validation=None):
        self.id_ = id_
        self.path_params = path_params
        self.query_params = query_params
        self.body = body
        self.validation = validation

    def __str__(self):
        return str(self.__dict__)


class Argus:
    def __init__(self, test_folder, config_fpath, out_fpath=None):
        self.test_folder = test_folder
        self.config_fpath = config_fpath
        with open(config_fpath, 'r') as fhand:
            self.config = yaml.safe_load(fhand)

        if out_fpath is None:
            t = datetime.now().strftime('%Y%m%d%H%M%S')
            self.out_fpath = os.path.join(test_folder,
                                          'argus_out_' + t + '.json')
        else:
            self.out_fpath = out_fpath

        self.suites = []

        self.suite_ids = []
        self.test_ids = []
        self.task_ids = []

        self.suite = None
        self.test = None
        self.task = None
        self.token = None
        self.url = None
        self.headers = {}
        self.response = None
        self.async_jobs = []
        self.validation_results = []

        self._parse_files(self.test_folder)
        self._add_default_query_params()
        self._generate_headers()
        self._generate_token()

        if 'validator' in self.config:
            validator = self.config['validator']
            module = importlib.import_module('.'.join(['argus', validator]))
            cls_name = ''.join(x.title() for x in validator.split('_'))
            validator_class = getattr(module, cls_name)
            self.validator = validator_class(config=self.config)
        else:
            self.validator = Validator(config=self.config)

    def _add_default_query_params(self):
        if self.config['rest'] and self.config['rest']['queryParams']:
            default_params = self.config['rest']['queryParams']
            for suite in self.suites:
                for test in suite.tests:
                    for task in test.tasks:
                        for key in default_params:
                            if key not in task.query_params:
                                task.query_params[key] = default_params[key]

    def _generate_headers(self):
        if self.config['rest'] and self.config['rest']['headers']:
            self.headers = self.config['rest']['headers']

    @staticmethod
    def _login(auth, field):
        url = create_url(auth['url'], auth.get('pathParams'),
                         auth.get('queryParams'))
        response = query(url, auth.get('method'), auth.get('headers'),
                         auth.get('body'))
        return get_item(response.json(), field)

    def _generate_token(self):
        if 'authentication' in self.config:
            auth = self.config['authentication']
            token_func = re.findall(r'^(.+)\((.+)\)$', auth['token'])
            if token_func:
                if token_func[0][0] == 'env':
                    self.token = os.environ(token_func[1])
                elif token_func[0][0] == 'login':
                    self.token = self._login(auth, token_func[0][1])
            else:
                self.token = auth['token']
            self.headers['Authorization'] = 'Bearer {}'.format(self.token)

    # def _filter_suite(self, suite):
    #     if 'suites' in self.config and suite.id_ not in self.config['suites']:
    #         return None
    #     if 'tests' in self.config:
    #         if 'ignore_method' in self.config['tests']:
    #             if test.method in self.config['tests']['ignore_method']:
    #                 return None
    #
    #
    #     return suite

    def _parse_files(self, test_folder):
        fpaths = [os.path.join(test_folder, file)
                  for file in os.listdir(test_folder)
                  if os.path.isfile(os.path.join(test_folder, file)) and
                  file.endswith('.yml')]
        for fpath in fpaths:
            with open(fpath, 'r') as fhand:
                suite = yaml.safe_load(fhand)
            # suite = self._filter_suite(self._parse_suite(suite))
            suite = self._parse_suite(suite)
            if suite is not None:
                self.suites.append(suite)

    def _parse_suite(self, suite):
        id_ = suite.get('id')
        if id_ is None:
            raise ValueError('Field "id" is required for each suite')
        if id_ in self.suite_ids:
            raise ValueError('Duplicated suite IDs "{}"'.format(id_))
        self.suite_ids.append(id_)

        base_url = suite.get('baseUrl')

        tests = list(filter(
            None, [self._parse_test(test) for test in suite.get('tests')]
        ))

        suite = _Suite(id_=id_, base_url=base_url, tests=tests)

        return suite

    def _parse_test(self, test):
        id_ = test.get('id')
        if id_ is None:
            raise ValueError('Field "id" is required for each test')
        if id_ in self.test_ids:
            raise ValueError('Duplicated test ID "{}"'.format(id_))
        self.test_ids.append(id_)

        tags = test.get('tags')
        path = test.get('path')
        method = test.get('method')
        async_ = test.get('async')

        tasks = []
        for task in test.get('tasks'):
            tasks += self._parse_task(task)

        test = _Test(id_=id_, tags=tags, path=path, method=method,
                     async_=async_, tasks=tasks)
        return test

    @staticmethod
    def _parse_content(params):
        for field in params:
            if isinstance(params[field], dict) and field != 'matrixParams':
                if 'file' in params[field]:
                    fpath = params[field]['file']
                    if fpath.endswith('.gz'):
                        lines = gzip.open(fpath, 'r').readlines()
                    else:
                        lines = open(fpath, 'r').readlines()
                    params[field] = ','.join(lines)
                if 'env' in params[field]:
                    env_var = os.environ(params[field]['env'])
                    params[field] = env_var
        return params

    @staticmethod
    def _parse_matrix_params(matrix_params):
        keys, values = list(matrix_params.keys()), list(matrix_params.values())
        value_product = list(product(*values))
        matrix_params = [
            dict(j) for j in [list(zip(keys, i)) for i in value_product]
        ]
        return matrix_params

    @staticmethod
    def _merge_params(task_id, query_params, matrix_params_list):
        query_params_list = []
        query_params = query_params or {}
        for matrix_params in matrix_params_list:
            new_query_params = query_params.copy()

            duplicated = list(set(matrix_params.keys()) &
                              set(new_query_params.keys()))
            if duplicated:
                msg = '[Task ID: "{}"] Some matrixParams are already' \
                      ' defined in queryParams ("{}")'
                raise ValueError(
                    msg.format(task_id, '";"'.join(duplicated)))

            new_query_params.update(matrix_params)
            query_params_list.append(new_query_params)
        return query_params_list

    def _parse_task(self, task):
        # Getting task ID
        id_ = task.get('id')
        if id_ is None:
            raise ValueError('Field "id" is required for each task')
        if id_ in self.task_ids:
            raise ValueError('Duplicated task ID "{}"'.format(id_))
        self.task_ids.append(id_)

        path_params = task.get('pathParams')
        query_params = task.get('queryParams')
        matrix_params = task.get('matrixParams')
        body = task.get('body')
        validation = task.get('validation')

        # Parsing pathParams and queryParams
        if path_params is not None:
            path_params = self._parse_content(path_params)
        if query_params is not None:
            query_params = self._parse_content(query_params)

        # Parsing matrix params
        if matrix_params is not None:
            matrix_params_list = self._parse_matrix_params(matrix_params)
            query_params_list = self._merge_params(id_, query_params,
                                                   matrix_params_list)
        else:
            query_params_list = [query_params]

        # Generating ID list
        id_list = [
            '{}-{}'.format(id_, i) for i in range(len(query_params_list))
        ] if len(query_params_list) > 1 else [id_]

        # Creating tasks
        tasks = [
            _Task(id_=id_, path_params=path_params,
                  query_params=query_params_list[i], body=body,
                  validation=validation)
            for i, id_ in enumerate(id_list)
        ]

        return tasks

    def query_task(self):
        url = '/'.join(s.strip('/') for s in [self.suite.base_url,
                                              self.test.path])
        self.url = create_url(url, self.task.path_params,
                              self.task.query_params)
        response = query(self.url, self.test.method, self.headers,
                         self.task.body)
        self.response = response

    def execute(self):
        validation_results = []
        out_fhand = open(self.out_fpath, 'w')
        for suite in self.suites:
            self.suite = suite
            for test in suite.tests:
                self.test = test
                for task in self.test.tasks:
                    self.task = task
                    self.query_task()
                    if not self.test.async_:
                        res = self.validator.validate(self.response,
                                                      self.task)
                        vr = ValidationResult(
                            suite_id=self.suite.id_,
                            test_id=self.test.id_,
                            task_id=self.task.id_,
                            url=self.url,
                            headers=self.headers,
                            tags=self.test.tags,
                            method=self.test.method,
                            async_=self.test.async_,
                            time=self.response.elapsed.total_seconds(),
                            params=self.task.query_params,
                            status_code=self.response.status_code,
                            validation=res,
                            status=all(
                                [v['result'] for v in res]
                            )
                        )
                        validation_results.append(vr)

                    else:
                        self.async_jobs.append(
                            {
                                'suite': self.suite,
                                'test': self.test,
                                'task': self.task,
                                'url': self.url,
                                'headers': self.headers,
                                'response': self.response
                            }
                        )
            if self.async_jobs:
                async_res = self.validator.validate_async(self.async_jobs)
                validation_results += async_res

            out_fhand.write('\n'.join([json.dumps(vr.to_json())
                                       for vr in validation_results]))
        out_fhand.close()
