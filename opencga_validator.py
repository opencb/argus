import re
import requests
import time
import logging

from dargus.validator import Validator
from dargus.utils import num_compare

LOGGER = logging.getLogger('argus_logger')


class OpencgaValidator(Validator):
    def __init__(self, config, auth_token):
        super().__init__(config=config, auth_token=auth_token)

    def validate_response(self, response):
        response_json = response.json()
        if 'events' in response_json['responses'][0] and response_json['responses'][0]['events']:
            for event in response_json['responses'][0]['events']:
                if event['type'] == 'ERROR':
                    LOGGER.error('Event: "{}"'.format(event))
                    return False, event
        return True, None

    def validate_async_response(self, async_response):
        async_response_json = async_response.json()
        async_response_json = async_response_json['responses'][0]['results'][0]
        if async_response_json['internal']['status']['id'] in ['ABORTED', 'ERROR']:
            event = async_response_json['execution']['events'][0]['message']
            LOGGER.error('Event: "{}"'.format(event))
            return False, event
        return True, None

    @staticmethod
    def get_job_info(job_id, study_id, base_url, headers):
        ws_url = re.findall('(^http.+rest/v[0-9]+)', base_url)[0]
        path = '/jobs/{}/info?study={}'.format(job_id, study_id)
        url = '/'.join(s.strip('/') for s in [ws_url, path])
        job_response = requests.get(url, headers=headers)
        return job_response

    @staticmethod
    def check_job_status(job_res_json):
        job_res_json = job_res_json['responses'][0]['results'][0]
        if job_res_json['internal']['status']['id'] in ['PENDING', 'RUNNING', 'QUEUED']:
            return False
        return True

    def get_async_response_for_validation(self, response, current, url, method, headers, auth_token):
        res_json = response.json()

        # Waiting for job to end so it can be validated
        while True:
            # Getting job info
            job_response = self.get_job_info(
                study_id=res_json['responses'][0]['results'][0]['study']['id'],
                job_id=res_json['responses'][0]['results'][0]['id'],
                base_url=current.base_url,
                headers=headers
            )
            job_res_json = job_response.json()

            # Validate only if job has ended
            if self.check_job_status(job_res_json):
                break
            time.sleep(self.validation['asyncRetryTime'])
        return job_response

    def file_exists(self, files, fname_list):
        files_value = self.get_item(files)
        if isinstance(fname_list, str):
            fname_list = fname_list.split(',')
        out_fnames = [file['name'] for file in files_value if 'name' in file]
        intersection = [fname for fname in fname_list if fname in out_fnames]
        if len(intersection) == len(fname_list):
            return True
        return False

    def file_size(self, files, fname, size, operator='eq'):
        files_value = self.get_item(files)
        for file in files_value:
            if 'name' in file:
                if file['name'] == fname:
                    return num_compare(file['size'], size, operator)
        return False

    def opencga_query(self, path, variable_name):
        # Getting base URL from config or from the suite itself
        base_url = None
        if self._config.get('baseUrl') is not None:
            base_url = self._config.get('baseUrl')
        if self._current.base_url is not None:
            base_url = self._current.base_url

        # Querying the endpoint and storing the response internally
        response = requests.get(base_url + path,
                                headers={"Authorization": 'Bearer {}'.format(self._auth_token)})
        self._stored_values[variable_name] = response.json()

        return True
