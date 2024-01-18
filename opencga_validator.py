import os
import re
import requests
import time
import logging
import gzip
import subprocess

from dargus.validator import Validator
from dargus.utils import num_compare

LOGGER = logging.getLogger('argus_logger')


class OpencgaValidator(Validator):
    def __init__(self, config, auth_token):
        super().__init__(config=config, auth_token=auth_token)

    def validate_response(self, response):
        response_json = response.json()
        events = []
        if 'events' in response_json and response_json['events']:
            events = response_json['events']
        if 'events' in response_json['responses'][0] and response_json['responses'][0]['events']:
            events = response_json['events']
        if events:
            for event in events:
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

    def validate_allele_freqs(self, variants, r_squared):
        # Getting cohort variant allele frequencies from opencga
        variant_id_list = []
        opencga_cohort_freqs = {}
        for variant_data in self.get_item(variants):
            variant_id = 'chr{}:{}:{}:{}'.format(variant_data['chromosome'], variant_data['start'],
                                                 variant_data['reference'], variant_data['alternate'])
            variant_id_list.append(variant_id)
            opencga_cohort_freqs[variant_id] = {cohort_data['cohortId']: cohort_data['altAlleleFreq']
                                                for cohort_data in variant_data['studies'][0]['stats']
                                                if cohort_data['cohortId'] in ['EUR', 'EAS', 'AMR', 'SAS', 'AFR']}

        # Getting cohort variant allele frequencies from reference VCF
        reference_vcf_fpath = os.path.join(
            self._config['workingDir'], 'validation-cohort',
            '20201028_CCDG_14151_B01_GRM_WGS_2020-08-05_chr22.recalibrated_variants.subset_1000.vcf.gz'
        )
        reference_vcf_cohort_freqs = {}
        for line in gzip.open(reference_vcf_fpath, 'r'):
            line = line.decode()
            if line.startswith('#'):  # Skip VCF header
                continue
            line_items = line.split()
            if ',' in line_items[3] or ',' in line_items[4]:  # Skip multiallelic variants
                continue
            variant_id = '{}:{}:{}:{}'.format(line_items[0], line_items[1], line_items[3], line_items[4])
            reference_vcf_cohort_freqs[variant_id] = {
                key_value.split('=')[0][3:]: float(key_value.split('=')[1])
                for key_value in line.split()[7].split(';')
                if '=' in key_value and key_value.split('=')[0] in ['AF_EUR', 'AF_EAS', 'AF_AMR', 'AF_SAS', 'AF_AFR']
            }

        # Writing allele frequencies
        out_fhand = open(os.path.join(self._config['workingDir'], 'validation-cohort', 'out', 'out.tsv'), 'w')
        out_fhand.write('\t'.join(['id', 'cohort', 'opencga', 'reference']) + '\n')
        for id_ in variant_id_list:
            if id_ in opencga_cohort_freqs and id_ in reference_vcf_cohort_freqs:
                for cohort in ['EUR', 'EAS', 'AMR', 'SAS', 'AFR']:
                    line = '\t'.join(map(str, [id_, cohort, opencga_cohort_freqs[id_][cohort],
                                               reference_vcf_cohort_freqs[id_][cohort]]))
                    out_fhand.write(line + '\n')
        out_fhand.close()

        # Plotting regression line with Rscript
        cmd = ["/usr/bin/Rscript",
               "--vanilla",
               os.path.join(self._config['workingDir'], 'validation-cohort', 'allele_freqs.R'),
               os.path.join(self._config['workingDir'], 'validation-cohort', 'out', 'out.tsv'),
               os.path.join(self._config['workingDir'], 'validation-cohort', 'out')]
        result = subprocess.run(cmd, capture_output=True)

        if float(result.stdout.split()[1]) < float(r_squared):
            return False
        return True
