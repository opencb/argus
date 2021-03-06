import re
import requests
import time

from argus.validator import Validator
from argus.validation_result import ValidationResult


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
        job_res_json = job_res_json['response'][0]['result'][0]
        if job_res_json['status']['name'] in ['PENDING', 'RUNNING']:
            return False
        return True

    def validate_async(self, async_jobs):
        validation_results = [None]*len(async_jobs)
        finished_jobs = []
        while True:
            for i, async_job in enumerate(async_jobs):
                if i in finished_jobs:
                    continue
                res_json = async_job['response'].json()
                job_response = self.get_job_info(
                    study_id=res_json['response'][0]['result'][0]['study']['id'],
                    job_id=res_json['response'][0]['result'][0]['id'],
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
            time.sleep(self.validation['validation']['asyncRetryTime'])
        return validation_results
