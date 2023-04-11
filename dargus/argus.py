import os
import yaml
import gzip
import re
import json
from itertools import product
from datetime import datetime

from dargus.validator import Validator
from dargus.validation_result import ValidationResult
from dargus.utils import get_item, create_url
from dargus.commons import query


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
    def __init__(self, test_folder, argus_config, out_fpath=None):
        self.test_folder = test_folder

        self.config = argus_config

        if out_fpath is None:
            t = datetime.now().strftime('%Y%m%d%H%M%S')
            self.out_fpath = os.path.join(test_folder, 'argus_out_' + t + '.json')
        else:
            os.makedirs(os.path.dirname(out_fpath), exist_ok=True)
            self.out_fpath = out_fpath

        self.suites = []

        self.suite_ids = []
        self.test_ids = []
        self.task_ids = []

        self.current = None
        self.test = None
        self.task = None
        self.token = None
        self.url = None
        self.headers = {}
        self.response = None
        self.async_jobs = []
        self.validation_results = []

        self._parse_files(self.test_folder)
        self._generate_headers()
        self._generate_token()

        if 'validator' in self.config and self.config['validator'] is not None:
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
                validation=self.config.get('validation')
            )
        else:
            self.validator = Validator(
                validation=self.config.get('validation')
            )

    def _generate_headers(self):
        if 'rest' in self.config and self.config['rest'] is not None and self.config['rest']['headers']:
            self.headers = self.config['rest']['headers']

    @staticmethod
    def _login(auth, field):
        url = create_url(auth['url'], auth.get('pathParams'),
                         auth.get('queryParams'))
        response = query(url, method=auth.get('method'), headers=auth.get('headers'), body=auth.get('body'))
        return get_item(response.json(), field)

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
            with open(fpath, 'r') as fhand:
                suite = yaml.safe_load(fhand)
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

        tasks = []
        for task in test.get('tasks'):
            tasks += list(filter(None, self._parse_task(task)))

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
                    env_var = os.environ[params[field]['env']]
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
        body_matrix_params = task.get('bodyMatrixParams')
        validation = task.get('validation')

        # Parsing pathParams and queryParams
        if path_params is not None:
            path_params = self._parse_content(path_params)
        if query_params is not None:
            query_params = self._parse_content(query_params)

        # Parsing matrix params
        if matrix_params is not None:
            matrix_params_list = self._parse_matrix_params(matrix_params)
            query_params_list = self._merge_params(id_, query_params, matrix_params_list)
        else:
            query_params_list = [query_params]

        # Adding default queryParams
        if 'rest' in self.config and self.config['rest'] is not None and self.config['rest']['queryParams']:
            default_params = self.config['rest']['queryParams']
            for query_params in query_params_list:
                for key in default_params:
                    if key not in query_params:
                        query_params[key] = default_params[key]

        # Parsing body matrix params
        if body_matrix_params is not None:
            matrix_body_params_list = self._parse_matrix_params(body_matrix_params)
            body_params_list = self._merge_params(id_, body, matrix_body_params_list)
        else:
            body_params_list = [body]

        # Cartesian product between query and body params
        task_params = [i for i in product(query_params_list, body_params_list)]

        # Generating ID list
        id_list = [
            '{}-{}'.format(id_, i+1) for i in range(len(task_params))
        ] if len(task_params) > 1 else [id_]

        # Creating tasks
        tasks = [
            _Task(id_=id_, path_params=path_params,
                  query_params=task_params[i][0], body=task_params[i][1],
                  validation=validation)
            for i, id_ in enumerate(id_list)
        ]

        return list(filter(None, tasks))

    def query_task(self):
        url = '/'.join(s.strip('/') for s in [self.current.base_url,
                                              self.current.tests[0].path])
        self.url = create_url(url, self.current.tests[0].tasks[0].path_params,
                              self.current.tests[0].tasks[0].query_params)
        response = query(self.url, method=self.current.tests[0].method, headers=self.headers,
                         body=self.current.tests[0].tasks[0].body)
        self.response = response

    def execute(self):
        validation_results = []
        out_fhand = open(self.out_fpath, 'w')
        for suite in self.suites:
            self.current = suite
            for test in suite.tests:
                self.current.tests = [test]
                for task in test.tasks:
                    self.current.tests[0].tasks = [task]
                    self.query_task()
                    if not self.current.tests[0].async_:
                        res = self.validator.validate(
                            self.response, self.current.tests[0].tasks[0]
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

        out_fhand.write('\n'.join([json.dumps(vr.to_json())
                                   for vr in validation_results]) + '\n')
        out_fhand.close()
