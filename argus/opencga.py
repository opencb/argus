#!/usr/bin/env python3

import sys
import argparse
import requests
import getpass
import re
import time

from argus import Argus
from validator import ValidationResult


class Opencga(Argus):
    def __init__(self, test_yml, user):
        super().__init__(test_yml)

        self.user = user
        self.token = None
        self.headers = None
        self.ws_url = None

        self.login()

    def get_webservices_url(self):
        self.ws_url = re.findall('(^http.+rest/v[0-9]+)', self.base_url)[0]

    def login(self):
        self.get_webservices_url()
        path = '/users/{user}/login'.format(user=self.user)
        url = '/'.join(s.strip('/') for s in [self.ws_url, path])
        response = requests.post(url, json={'password': getpass.getpass()})
        self.token = response.json()['response'][0]['result'][0]['token']

    def get_headers(self):
        self.headers = {
            "Accept-Encoding": "gzip",
            "Authorization": 'Bearer {}'.format(self.token)
        }
        return self.headers

    def validate(self):
        pass
        # res = self.response.json()
        # print(res)
        # vr = ValidationResult(
        #     id_=self.task.id_,
        #     url=self.url,
        #     headers=self.headers,
        #     api_version=res['apiVersion'],
        #     status_code=self.response.status_code,
        #     num_results=res['response'][0]['numResults']
        # )
        # self.validation_results.append(vr)

    def validate_async(self):
        pass
        # validation_results = [None]*len(self.async_jobs)
        # finished_jobs = []
        # while True:
        #     for i, async_job in enumerate(self.async_jobs):
        #         if i in finished_jobs:
        #             continue
        #         res_json = async_job['response'].json()
        #         job_info = self.get_job_info(
        #             res_json['response'][0]['result'][0]['uuid'],
        #             res_json['response'][0]['result'][0]['studyUuid']
        #         )
        #         if self.check_job_status(job_info):
        #             vr = ValidationResult(
        #                 id_=async_job['task'].id_,
        #                 url=async_job['url'],
        #                 headers=async_job['headers'],
        #                 api_version=res_json['apiVersion'],
        #                 status_code=async_job['response'].status_code,
        #                 num_results=job_info['response'][0]['numResults']
        #             )
        #             validation_results[i] = vr
        #             finished_jobs.append(i)
        #     if None not in validation_results:
        #         break
        #     time.sleep(self.async_retry_time)
        # self.validation_results += validation_results

    def get_job_info(self, job_id, study_id):
        path = '/jobs/{}/info?study={}'.format(job_id, study_id)
        url = '/'.join(s.strip('/') for s in [self.ws_url, path])
        job_info = requests.get(url, headers=self.headers).json()
        return job_info

    @staticmethod
    def check_job_status(job_info):
        job_info = job_info['response'][0]['result'][0]
        if job_info['status']['name'] in ['PENDING', 'RUNNING']:
            return False
        return True


def _setup_argparse():
    desc = 'This script test automatically all defined tests'
    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument('test_yml_fpath', help='test YML file path')
    parser.add_argument('user', help='OpenCGA user')
    args = parser.parse_args()
    return args


def main():
    # Getting arg parameters
    args = _setup_argparse()

    client_generator = Opencga(args.test_yml_fpath, args.user)
    client_generator.execute()


if __name__ == '__main__':
    sys.exit(main())
