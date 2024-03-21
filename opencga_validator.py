import os
import re
import requests
import time
import logging

from dargus.validator import Validator
from dargus.utils import create_url, query, get_item_from_json, num_compare, plot_regression_line

LOGGER = logging.getLogger('argus_logger')


class OpencgaValidator(Validator):
    def __init__(self, config):
        super().__init__(config=config)

    def login(self):
        # Getting authorisation token from config
        auth_token = None
        if 'authentication' in self._config and self._config['authentication'] is not None:
            auth_info = self._config['authentication']
            token_func = re.findall(r'^(.+)\((.+)\)$', auth_info['token'])
            if token_func:
                if token_func[0][0] == 'env':
                    auth_token = os.environ[token_func[1]]
                elif token_func[0][0] == 'login':
                    url = create_url(url=auth_info['url'],
                                     path_params=auth_info.get('pathParams'),
                                     query_params=auth_info.get('queryParams'))
                    LOGGER.debug('Logging in: {} {} {}'.format(auth_info.get('method'), url, auth_info.get('bodyParams')))
                    response = query(url,
                                     method=auth_info.get('method'),
                                     headers=auth_info.get('headers'),
                                     body=auth_info.get('bodyParams'))
                    auth_token = get_item_from_json(response.json(), token_func[0][1])
            else:
                auth_token = auth_info.get('token')

        # Adding authorisation token to headers
        if auth_token:
            headers = self._config.setdefault('headers', {})
            headers.update({'Authorization': 'Bearer {}'.format(auth_token)})

    def validate_response(self, response):
        if response is None:
            return False, 'The webservice returned an empty response'
        try:
            response_json = response.json()
        except requests.exceptions.JSONDecodeError:
            return False, 'The webservice is not responding with a proper JSON'
        events = []
        if 'events' in response_json and response_json['events']:
            events = response_json['events']
        if 'events' in response_json['responses'][0] and response_json['responses'][0]['events']:
            events = response_json['responses'][0]['events']
        if events:
            for event in events:
                if event['type'] == 'ERROR':
                    LOGGER.error('Event: "{}"'.format(event))
                    return False, event
        return True, None

    def validate_async_response(self, async_response):
        if async_response is None:
            return False, 'The webservice returned an empty response'
        try:
            async_response_json = async_response.json()
        except requests.exceptions.JSONDecodeError:
            return False, 'The webservice is not responding with a proper JSON'
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

    def get_async_response_for_validation(self, response, current):
        res_json = response.json()

        # Waiting for job to end so it can be validated
        while True:
            # Getting job info
            job_response = self.get_job_info(
                study_id=res_json['responses'][0]['results'][0]['study']['id'],
                job_id=res_json['responses'][0]['results'][0]['id'],
                base_url=current.base_url,
                headers=current.tests[0].headers
            )
            job_res_json = job_response.json()

            # Validate only if job has ended
            if self.check_job_status(job_res_json):
                break
            time.sleep(self.validation['asyncRetryTime'])
            self.login()
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
        if self.current.base_url is not None:
            base_url = self.current.base_url

        # Querying the endpoint and storing the response internally
        response = requests.get(url=base_url + path, headers=self.current.tests[0].headers)
        self._stored_values[variable_name] = response.json()

        return True

    def check_cohort_allele_freqs(self, opencga_variants, reference_fpath, r_squared):
        # Getting cohort variant allele frequencies from opencga
        variant_id_list = []
        opencga_cohort_freqs = {}
        for variant_data in self.get_item(opencga_variants):
            variant_id = 'chr{}:{}:{}:{}'.format(variant_data['chromosome'], variant_data['start'],
                                                 variant_data['reference'], variant_data['alternate'])
            variant_id_list.append(variant_id)
            opencga_cohort_freqs[variant_id] = {cohort_data['cohortId']: cohort_data['altAlleleFreq']
                                                for cohort_data in variant_data['studies'][0]['stats']
                                                if cohort_data['cohortId'] in ['EUR', 'EAS', 'AMR', 'SAS', 'AFR']}

        # Getting cohort variant allele frequencies from reference file
        reference_fpath = os.path.realpath(os.path.expanduser(reference_fpath))
        reference_fhand = open(reference_fpath, 'r')
        reference_fhand.readline()  # Skip header
        reference_cohort_freqs = {}
        for line in reference_fhand:
            variant_id, cohort, cohort_freq = line.split()
            reference_cohort_freqs.setdefault(variant_id, {}).update({cohort: cohort_freq})

        # Writing allele frequencies
        cohort_freqs_fpath = os.path.join(self.current.output_dir, 'cohort_freqs_comparison.tsv')
        cohort_freqs_fhand = open(cohort_freqs_fpath, 'w')
        cohort_freqs_fhand.write('\t'.join(['id', 'opencga', 'reference', 'cohort']) + '\n')
        for id_ in variant_id_list:
            if id_ in opencga_cohort_freqs and id_ in reference_cohort_freqs:
                for cohort in ['EUR', 'EAS', 'AMR', 'SAS', 'AFR']:
                    line = '\t'.join(map(str, [id_, opencga_cohort_freqs[id_][cohort],
                                               reference_cohort_freqs[id_][cohort], cohort]))
                    cohort_freqs_fhand.write(line + '\n')
        cohort_freqs_fhand.close()

        # Plotting regression line
        r_linreg = plot_regression_line(input_fpath=cohort_freqs_fpath,
                                        output_fpath=os.path.join(self.current.output_dir, 'linreg.png'))

        if float(r_linreg) <= float(r_squared):
            return False
        return True
