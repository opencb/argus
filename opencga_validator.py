import os
import re
import requests
import time
import logging
import gzip
import json
import random

from dargus.validator import Validator
from dargus.utils import create_url, query, get_item_from_json, num_compare, plot_regression_line

LOGGER = logging.getLogger('argus_logger')


class OpencgaValidator(Validator):
    def __init__(self, config):
        super().__init__(config=config)

    def login(self, verbose=True):
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
                    if verbose:
                        msg = 'Logging in: {} {} {}'.format(auth_info.get('method'), url, auth_info.get('bodyParams'))
                        LOGGER.debug(msg)
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
            self.login(verbose=False)
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

    def opencga_download(self, study, file_id):
        # Getting base URL from config or from the suite itself
        base_url = None
        if self._config.get('baseUrl') is not None:
            base_url = self._config.get('baseUrl')
        if self.current.base_url is not None:
            base_url = self.current.base_url

        # Getting download URL
        if file_id.startswith('$'):  # Stored value
            file_id = self._stored_values[file_id]
        url = base_url + '/files/{}/download?study={}'.format(file_id, study)

        # Querying the endpoint and storing the response internally
        response = requests.get(url, headers=self.current.tests[0].headers, stream=True)

        # Writing the file in outdir
        export_fpath = os.path.join(self.current.output_dir, file_id)
        with open(export_fpath, mode='wb') as file:
            for chunk in response.iter_content(chunk_size=10 * 1024):
                file.write(chunk)

        return os.path.isfile(export_fpath)

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
        cohort_freqs_fpath = os.path.join(self.current.output_dir, self.id_ + 'cohort_freqs_comparison.tsv')
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
                                        output_fpath=os.path.join(self.current.output_dir, self.id_ + 'linreg.png'))

        if float(r_linreg) <= float(r_squared):
            return False
        return True

    def check_export_file(self, export_fpath):
        summary = {}
        query_params = self.current.tests[0].steps[0].query_params
        body_params = self.current.tests[0].steps[0].body_params

        # Opening file
        if export_fpath.startswith('$'):  # Stored value
            export_fpath = self._stored_values[export_fpath]
        json_fhand = gzip.open(os.path.join(self.current.output_dir, export_fpath), 'r')
        if export_fpath.endswith('.vcf.gz'):
            # TODO Create a vcf2json function to validate VCF and JSON at the same time
            return False

        # Checking file is not empty
        observed_count = sum(1 for line in json_fhand)
        json_fhand.seek(0)
        if observed_count == 0:
            LOGGER.warning('File "{}" contains no variants'.format(export_fpath))
            return False

        # Initializing variant summary with variant IDs to contain validation for each variant
        var_summary = {json.loads(line)['id']: {} for line in json_fhand}
        json_fhand.seek(0)  # Returning file handle to the first line

        # Checking number of variants returned
        if 'limit' in body_params:
            expected_count = body_params['limit']
            summary['count'] = True if expected_count >= observed_count else False
            json_fhand.seek(0)  # Returning file handle to the first line

        # Checking consequence types
        if 'ct' in body_params:
            expected_cts = body_params['ct'].split(',')
            for i, variant in enumerate(json_fhand):
                variant = json.loads(variant)
                observed_cts = set([ct['name']
                                    for ct_list in variant['annotation']['consequenceTypes']
                                    for ct in ct_list['sequenceOntologyTerms']])
                var_summary[variant['id']]['ct'] = True if observed_cts.intersection(expected_cts) else False
            summary['ct'] = all([var_summary[v]['ct'] for v in var_summary])
            json_fhand.seek(0)  # Returning file handle to the first line

        # If "includeSampleId" is not in bodyParams and is not True/'True'/'true', "studies.samples.sampleId" is null
        include_sample_id = True if str(body_params.get('includeSampleId')).lower() == 'true' else False
        if not include_sample_id:
            msg = 'Parameter "includeSampleId" is False. Skipping checks for sample and sampleData.'
            LOGGER.warning(msg)

        # Getting observed sample FORMAT data
        observed_sd = {}  # e.g. {'1:1915326:G:A': {'NA12877': {'GT': '0/1', 'GQ': '194'}
        if ('sample' in body_params or 'sampleData' in body_params) and include_sample_id:
            for i, variant in enumerate(json_fhand):
                variant = json.loads(variant)
                variant_sd = {}
                for study_data in variant['studies']:
                    if study_data['studyId'].split(':')[-1] == query_params['study'].split(':')[-1]:
                        for sample_data in study_data['samples']:
                            data = {k: v for k, v in zip(study_data['sampleDataKeys'], sample_data['data'])}
                            variant_sd[str(sample_data['sampleId'])] = data
                observed_sd[variant['id']] = variant_sd
            json_fhand.seek(0)

        # Checking sample (e.g. HG0097:0/0;HG0096;HG0095;HG0098:0/1,1/1;HG0050:0|1,1|2,2/1)
        if 'sample' in body_params and include_sample_id:
            # Parsing sample filter
            op = list(set(re.findall('([,;])(?!\d[/|]\d)', body_params['sample'])))  # AND (;) or OR (,) or nothing
            op = op[0] if op else ';'
            sample_groups = re.split('[,;](?!\d[/|]\d)', body_params['sample'])
            expected_samples = [re.findall('^([a-zA-Z0-9_.]+)', sample_group)[0] for sample_group in sample_groups]
            expected_genotypes = [re.split('^[a-zA-Z0-9_.]+:*', sample_group)[1].split(',')
                                  for sample_group in sample_groups]

            # Checking that every variant has the expected samples and genotypes
            for variant in observed_sd:
                matches = [  # Stores True/False for each sample
                    (observed_sd[variant][sample]['GT'] in expected_genotypes[i]
                     if list(filter(None, expected_genotypes[i])) else True)  # if no gt, all gts are fine
                    if sample in observed_sd[variant].keys() else False
                    for i, sample in enumerate(expected_samples)
                ]
                var_summary[variant]['sample'] = (op == ';' and all(matches)) or (op == ',' and any(matches))
            summary['sample'] = all([var_summary[v]['sample'] for v in var_summary])

        # Checking sampleData (e.g. HG0097:DP>200;GT=1/1,0/1;HG0098:DP<10)
        if 'sampleData' in body_params and include_sample_id:
            # Parsing sampleData filter
            op = list(set(re.findall('([,;])[a-zA-Z0-9_.]+:', body_params['sampleData'])))
            op = op[0] if op else ';'  # AND (;) or OR (,)
            expected_samples = re.findall('[,;]*([a-zA-Z0-9_.]+):', body_params['sampleData'])
            if expected_samples:  # If sample is specified (e.g. HG0097:DP>200;GT=1/1)
                expected_sd = re.split('[,;]*[a-zA-Z0-9_.]+:', body_params['sampleData'])[1:]
            else:  # If no sample is specified (e.g. DP>200;GT=1/1), all samples from "sample" filter are used
                sample_groups = re.split('[,;](?!\\d[/|]\\d)', body_params['sample'])
                expected_samples = [re.findall('^([a-zA-Z0-9_.]+)', sample_group)[0] for sample_group in sample_groups]
                expected_sd = [body_params['sampleData']]*len(expected_samples)
            expected_sample_data = [item.split(';') for item in expected_sd]
            # Getting operators that split different fields (e.g. DP>200;GT=1/1,0/1 --> [';'])
            expected_sd_ops = [j[0] for j in [re.findall('([,;])(?=[a-zA-Z0-9_.]+[=><]{1,2})', i) or [';']
                                              for i in expected_sd]]

            # Checking that every variant complies with the expected filtered values
            for variant in observed_sd:
                matches = []  # Stores True/False for each sample
                for i, sample in enumerate(expected_samples):
                    field_matches = []  # Stores True/False for each format field
                    exp_sample_data = expected_sample_data[i]
                    exp_sd_op = expected_sd_ops[i]
                    if sample not in observed_sd[variant]:
                        field_matches.append(False)
                    else:
                        obs_sample_data = observed_sd[variant][sample]
                        for field in exp_sample_data:
                            field_name, symbol, expected_value = re.findall('([a-zA-Z0-9_.]+)([><=]+)(.+)', field)[0]
                            observed_value = obs_sample_data[field_name]
                            if symbol == '=':  # e.g. DP=20
                                symbol = '=='
                            if not expected_value.replace('.', '').replace('-', '').isdigit():
                                expected_value = '"{}"'.format(expected_value)
                            if not observed_value.replace('.', '').replace('-', '').isdigit():
                                observed_value = '"{}"'.format(observed_value)
                            if '/' in expected_value or '|' in expected_value:  # e.g. GT=0/1,1/1
                                expression = '{} in {}'.format(observed_value, expected_value.split(','))
                            else:
                                expression = '{}{}{}'.format(observed_value, symbol, expected_value)
                            field_matches.append(eval(expression))
                    matches.append(((exp_sd_op == ';' and all(field_matches)) or
                                    (exp_sd_op == ',' and any(field_matches))))
                var_summary[variant]['sampleData'] = (op == ';' and all(matches)) or (op == ',' and any(matches))
            summary['sampleData'] = all([var_summary[v]['sampleData'] for v in var_summary])

        # Getting observed QUAL, FILTER, INFO data
        observed_fd = {}  # e.g. {'1:1915326:G:A': {'NA12877': {'AN': '5', 'QUAL': '194'}
        if 'file' in body_params or 'fileData' in body_params:
            for i, variant in enumerate(json_fhand):
                variant = json.loads(variant)
                variant_fd = {}
                for study_data in variant['studies']:
                    if study_data['studyId'].split(':')[-1] == query_params['study'].split(':')[-1]:
                        for file_data in study_data['files']:
                            variant_fd[str(file_data['fileId'])] = file_data['data']
                observed_fd[variant['id']] = variant_fd
            json_fhand.seek(0)

        # Checking file
        if 'file' in body_params:
            expected_files = body_params['file'].split(',')
            for variant in observed_sd:
                var_summary[variant]['file'] = all([file in observed_fd[variant].keys() for file in expected_files])
            summary['file'] = all([var_summary[v]['file'] for v in var_summary])

        # Checking fileData (e.g. file_1.vcf:AN>200;DB=true;file_2.vcf:AN<10,FILTER=PASS,LowDP)
        if 'fileData' in body_params:
            # Parsing fileData filter
            expected_file_op = list(set(re.findall('([,;])[a-zA-Z0-9_.]+:', body_params['fileData'])))
            expected_file_op = expected_file_op[0] if expected_file_op else ';'  # AND (;) or OR (,)
            expected_files = re.findall('[,;]*([a-zA-Z0-9_.]+):', body_params['fileData'])
            if expected_files:  # If file is specified (e.g. file_1.vcf:AN>200;DB=true)
                expected_fd = re.split('[,;]*[a-zA-Z0-9_.]+:', body_params['fileData'])[1:]
            else:  # If no file is specified (e.g. AN>200), all files from "file" filter are used
                expected_files = body_params['file'].split(',')
                expected_fd = [body_params['fileData']] * len(expected_files)
            expected_file_data = [re.split('[,;](?=[a-zA-Z0-9_.]+[=><]{1,2})', item) for item in expected_fd]
            # Getting operators that split different fields (e.g. AN<10;FILTER=PASS,LowDP --> [';'])
            expected_fd_ops = [j[0] for j in [re.findall('([,;])(?=[a-zA-Z0-9_.]+[=><]{1,2})', i) or [';']
                                              for i in expected_fd]]

            # Checking that every variant complies with the expected filtered values
            for variant in observed_fd:
                matches = []  # Stores True/False for each sample
                for i, file in enumerate(expected_files):
                    field_matches = []  # Stores True/False for each fileData field
                    exp_file_data = expected_file_data[i]
                    exp_fd_op = expected_fd_ops[i]
                    if file not in observed_fd[variant]:
                        field_matches.append(False)
                    else:
                        obs_file_data = observed_fd[variant][file]
                        for field in exp_file_data:
                            field_name, symbol, expected_value = re.findall('([a-zA-Z0-9_.]+)([><=]+)(.+)', field)[0]
                            observed_value = obs_file_data[field_name]
                            if symbol == '=':  # e.g. FILTER=PASS
                                symbol = '=='
                            if not expected_value.replace('.', '').replace('-', '').isdigit():
                                expected_value = '"{}"'.format(expected_value)
                            if not observed_value.replace('.', '').replace('-', '').isdigit():
                                observed_value = '"{}"'.format(observed_value)
                            expression = '{}{}{}'.format(observed_value, symbol, expected_value)
                            field_matches.append(eval(expression))
                    matches.append(((exp_fd_op == ';' and all(field_matches)) or
                                    (exp_fd_op == ',' and any(field_matches))))
                var_summary[variant]['fileData'] = ((expected_file_op == ';' and all(matches)) or
                                                    (expected_file_op == ',' and any(matches)))
            summary['fileData'] = all([var_summary[v]['fileData'] for v in var_summary])

        # Creating variant summary
        variant_summary_fpath = os.path.join(self.current.output_dir, self.id_ + '.variant_summary.tsv')
        variant_summary_fhand = open(variant_summary_fpath, 'w')
        header_keys = ['id'] + list(var_summary[random.choice(list(var_summary.keys()))].keys())
        variant_summary_fhand.write('\t'.join(header_keys) + '\n')  # Header
        for variant in var_summary:
            line = '\t'.join([variant] + [str(var_summary[variant][k]) for k in header_keys if k != 'id']) + '\n'
            variant_summary_fhand.write(line)

        # Creating Summary
        filter_summary_fpath = os.path.join(self.current.output_dir, self.id_ + '.filter_summary.tsv')
        filter_summary_fhand = open(filter_summary_fpath, 'w')
        filter_summary_fhand.write('\t'.join(['id', 'status']) + '\n')  # Header
        for filter_ in summary:
            line = '\t'.join(map(str, [filter_, summary[filter_]])) + '\n'
            filter_summary_fhand.write(line)

        # Validation result
        if not all(summary[res] for res in summary):
            return False
        return True
