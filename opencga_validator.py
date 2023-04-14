import re
import requests
import time

from dargus.validator import Validator
from dargus.validation_result import ValidationResult
from dargus.utils import num_compare


class OpencgaValidator(Validator):
    def __init__(self, validation):
        super().__init__(validation=validation)

    @staticmethod
    def get_job_info(job_id, study_id, base_url, headers):
        ws_url = re.findall('(^http.+rest/v[0-9]+)', base_url)[0]
        path = '/jobs/{}/info?study={}'.format(job_id, study_id)
        url = '/'.join(s.strip('/') for s in [ws_url, path])
        job_response = requests.get(url, headers=headers)
        return job_response

    @staticmethod
    def check_job_status(job_response):
        job_res_json = job_response.json()
        job_res_json = job_res_json['responses'][0]['results'][0]
        if job_res_json['internal']['status']['id'] in ['PENDING', 'RUNNING', 'QUEUED']:
            return False
        return True

    def validate_async(self, async_jobs):
        validation_results = list([None]*len(async_jobs))
        finished_jobs = []
        while True:
            for i, async_job in enumerate(async_jobs):
                if i in finished_jobs:
                    continue
                res_json = async_job['response'].json()
                job_response = self.get_job_info(
                    study_id=res_json['responses'][0]['results'][0]['study']['id'],
                    job_id=res_json['responses'][0]['results'][0]['id'],
                    base_url=async_job['current'].base_url,
                    headers=async_job['headers']
                )
                if self.check_job_status(job_response):
                    res = self.validate(
                        job_response, async_job['current'].tests[0].tasks[0]
                    )
                    vr = ValidationResult(
                        current=async_job['current'],
                        url=async_job['url'],
                        response=job_response,
                        validation=res,
                        headers=async_job['headers'],
                    )
                    validation_results[i] = vr
                    finished_jobs.append(i)
            if None not in validation_results:
                break
            time.sleep(self.validation['asyncRetryTime'])
        return validation_results

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

    def file_contains(self, files, fname, pattern):
        pass
