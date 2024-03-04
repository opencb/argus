import os
import logging
import json
import yaml


LOGGER = logging.getLogger('argus_logger')


class ArgusConfiguration(object):
    def __init__(self, config_input, validator=None, suite_dir=None, suites=None, tags=None, input_dir=None,
                 output_dir=None, dry_run=None):
        self._config = {
            'validator': None,
            'suiteDir': None,
            'suites': None,
            'tags': None,
            'inputDir': None,
            'outputDir': None,
            'dry_run': None,
            'variables': {
                'INPUT_DIR': None,
                'OUTPUT_DIR': None
            }
        }

        self._load_config(config_input, validator, suite_dir, suites, tags, input_dir, output_dir, dry_run)
        LOGGER.debug('Configuration: {}'.format(self._config))

        self._validate_configuration()

    def _load_config(self, config_input, validator, suite_dir, suites, tags, input_dir, output_dir, dry_run):

        # Populating configuration
        if isinstance(config_input, dict):  # If it is a dictionary
            self._config.update(config_input)
        else:  # If it is a file (JSON or YAML)
            self._config.update(self._get_dictionary_from_file(config_input))

        # Setting up custom validator
        if validator is not None:
            self._config['validator'] = os.path.realpath(os.path.expanduser(validator))

        # Setting up suite directory
        if suite_dir is not None:
            self._config['suiteDir'] = os.path.realpath(os.path.expanduser(suite_dir))

        # Setting up suites to run
        if suites is not None:
            self._config['suites'] = suites.split(',')

        # Setting up tags to run
        if tags is not None:
            self._config['tags'] = tags.split(',')

        # Setting up input directory
        if not ('inputDir' in self._config and self._config['inputDir']):  # Default if not in main config
            self._config['inputDir'] = self._config['suiteDir']
        if input_dir is not None:  # Overwrite it if passed through CLI
            self._config['inputDir'] = os.path.realpath(os.path.expanduser(input_dir))
        self._config['variables']['INPUT_DIR'] = self._config['inputDir']  # Add to variables

        # Setting up output directory
        if not ('outputDir' in self._config and self._config['outputDir']):  # Default if not in main config
            self._config['outputDir'] = self._config['suiteDir']
        if output_dir is not None:  # Overwrite it if passed through CLI
            self._config['outputDir'] = os.path.realpath(os.path.expanduser(output_dir))
        self._config['variables']['OUTPUT_DIR'] = self._config['outputDir']  # Add to variables

        # Setting up tags to run
        if dry_run is not None:
            self._config['dry_run'] = dry_run

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
