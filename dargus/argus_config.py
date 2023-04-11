import json
import requests
import yaml


class ArgusConfiguration(object):
    def __init__(self, config_input, validator=None, username=None, password=None, suites=None):
        # Default config params
        self._config = {
            'authentication': None,
            'suites': None,
            'validation': None,
            'validator': None,
            'tests': None
        }

        self.load_config(config_input, validator, suites)

        self._validate_configuration(self._config)

    def load_config(self, config_input, validator, suites):
        if isinstance(config_input, dict):
            for key in config_input:
                self._config[key] = config_input[key]
        else:
            config_dict = self._get_dictionary_from_file(config_input)
            for key in config_dict:
                self._config[key] = config_dict[key]

        if validator is not None:
            self._config['validator'] = validator

        if suites is not None:
            self._config['suites'] = suites.split(',')


    @staticmethod
    def _get_dictionary_from_file(config_fpath):
        try:
            config_fhand = open(config_fpath, 'r')
        except IOError:
            msg = 'Unable to read file "' + config_fpath + '"'
            raise IOError(msg)

        config_dict = None
        if config_fpath.endswith('.yml') or config_fpath.endswith('.yaml'):
            config_dict = yaml.safe_load(config_fhand)

        if config_fpath.endswith('.json'):
            config_dict = json.loads(config_fhand.read())

        config_fhand.close()

        return config_dict

    @staticmethod
    def _validate_configuration(config):
        if config is None:
            raise ValueError('Missing configuration dictionary')

    @property
    def suites(self):
        return self._config['suites']

    @suites.setter
    def suites(self, new_suites):
        self._config['suites'] = new_suites

    @property
    def authentication(self):
        return self._config['authentication']

    @authentication.setter
    def authentication(self, new_authentication):
        self._config['authentication'] = new_authentication

    def get_config(self):
        return self._config
