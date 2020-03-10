import os
import sys
import yaml
import gzip
import re
import requests
from abc import ABC, abstractmethod
from itertools import product


class Test:
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


class Task:
    def __init__(self, id_, path_params=None, query_params=None, body=None,
                 validation=None):
        self.id_ = id_
        self.path_params = path_params
        self.query_params = query_params
        self.body = body
        self.validation = validation

    def __str__(self):
        return str(self.__dict__)


class Parent(ABC):
    def __init__(self, test_fpath):
        self.test_fpath = test_fpath

        self.id_ = None
        self.base_url = None
        self.async_retry_time = None
        self.time_deviation = None
        self.tests = None
        self.test = None
        self.task = None

        self.test_ids = []
        self.task_ids = []

        self.url = None
        self.headers = None
        self.response = None
        self.async_jobs = []
        self.validation_results = []

        self._parse_file(self.test_fpath)

    def _parse_file(self, test_fpath):
        with open(test_fpath, 'r') as fhand:
            info = yaml.safe_load(fhand)
        self.id_ = info.get('id')
        self.base_url = info.get('baseUrl')
        self.time_deviation = info.get('timeDeviation')
        self.async_retry_time = info.get('asyncRetryTime')
        self.tests = [self._parse_test(test) for test in info.get('tests')]

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

        test = Test(id_=id_, tags=tags, path=path, method=method,
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
            Task(id_=id_, path_params=path_params,
                 query_params=query_params_list[i], body=body,
                 validation=validation)
            for i, id_ in enumerate(id_list)
        ]

        return tasks

    def create_url(self):
        url = '/'.join(s.strip('/') for s in [self.base_url, self.test.path])
        if self.task.path_params is not None:
            try:
                url = url.format(**self.task.path_params)
            except KeyError as e:
                msg = 'Missing field in pathParams ({})'
                raise ValueError(msg.format(e))
        if self.task.query_params is not None:
            url += '?' + '&'.join(['{}={}'.format(k, self.task.query_params[k])
                                   for k in self.task.query_params])
        self.url = url

    @abstractmethod
    def get_headers(self):
        pass

    def query(self):
        self.create_url()
        headers = self.get_headers()
        # TODO
        sys.stderr.write('URL={}; HEADERS={}\n'.format(self.url, headers))
        if self.test.method.lower() == 'get':
            response = requests.get(self.url, headers=headers)
        elif self.test.method.lower() == 'post':
            response = requests.post(self.url, json=self.task.body,
                                     headers=headers)
        else:
            msg = 'Method "' + self.test.method + '" not implemented.'
            raise NotImplementedError(msg)
        self.response = response

    def validate_basic(self):
        task_time = self.task.validation.get('time')
        task_headers = self.task.validation.get('headers')
        task_status_code = self.task.validation.get('status_code')

        # TIME
        if task_time is not None:
            request_time = self.response.elapsed.total_seconds()
            max_time = task_time + task_time*self.time_deviation/100
            min_time = task_time - task_time*self.time_deviation/100
            if not min_time < request_time < max_time:
                sys.stderr.write('NOPE')  # TODO

        # HEADERS
        if task_headers is not None:
            for key in task_headers.keys():
                if key not in self.response.headers.keys() or \
                        self.response.headers[key] != task_headers[key]:
                    sys.stderr.write('NOPE')  # TODO

        # STATUS CODE
        if task_status_code is None:
            task_status_code = 200
        if not task_status_code == self.response.status_code:
            sys.stderr.write('NOPE')  # TODO


    @abstractmethod
    def validate(self):
        pass

    @abstractmethod
    def validate_async(self):
        pass

    @staticmethod
    def _get_item(path, json_dict):
        for item in path.split('.'):
            items = list(filter(None, re.split('\[|\]', item)))
            key, indexes = items[0], map(int, items[1:])
            json_dict = json_dict[key]
            if indexes:
                for i in indexes:
                    json_dict = json_dict[i]
        return json_dict

    def length(self, path, length, json_dict):
        return len(self._get_item(path, json_dict)) == length

    def execute(self):
        for test in self.tests:
            self.test = test
            for task in self.test.tasks:
                self.task = task
                self.query()
                self.validate_basic()
                if not self.test.async_:
                    self.validate()
                else:
                    self.async_jobs.append(
                        {
                            'test': self.test,
                            'task': self.task,
                            'url': self.url,
                            'headers': self.headers,
                            'response': self.response
                        }
                    )
        if self.async_jobs:
            self.validate_async()
