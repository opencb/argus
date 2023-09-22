import os
import logging
import json
import yaml


LOGGER = logging.getLogger('argus_logger')


class ArgusConfiguration(object):
    def __init__(self, config_input, validator=None, suites=None, working_dir=None):
        self._config = {}

        self.load_config(config_input, validator, suites, working_dir)
        LOGGER.debug('Configuration: {}'.format(self._config))

        self._validate_configuration()

    def load_config(self, config_input, validator, suites, working_dir):
        if isinstance(config_input, dict):
            for key in config_input:
                self._config[key] = config_input[key]
        else:
            config_dict = self._get_dictionary_from_file(config_input)
            for key in config_dict:
                self._config[key] = config_dict[key]

        if validator is not None:
            self._config['validator'] = os.path.realpath(os.path.expanduser(validator))

        if suites is not None:
            self._config['suites'] = suites.split(',')

        if working_dir is not None:
            self._config['workingDir'] = os.path.realpath(os.path.expanduser(working_dir))

    @staticmethod
    def _get_dictionary_from_file(config_fpath):
        LOGGER.debug('Loading configuration from: "{}"'.format(config_fpath))
        config_fpath = os.path.realpath(os.path.expanduser(config_fpath))
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

    def _validate_configuration(self):
        if self._config is None:
            raise ValueError('Missing configuration dictionary')

    def get_config(self):
        return self._config
