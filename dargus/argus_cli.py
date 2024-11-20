#!/usr/bin/env python3

import sys
import argparse
import logging

from dargus.argus import Argus
from dargus.argus_config import ArgusConfiguration
from dargus.utils import get_argus_version


class ArgusCLI:

    def __init__(self):
        self._parser = argparse.ArgumentParser(
            description='This program validates all defined tests for REST API Web Services'
        )

        # Adding parent parser with common arguments for subparsers
        self._parent_parser = argparse.ArgumentParser(add_help=False)
        self._parent()

        # Adding subparsers for each action
        self._subparsers = self._parser.add_subparsers()
        self._execute()
        # self._stats()

    @property
    def parser(self):
        return self._parser

    @parser.setter
    def parser(self, parser):
        self._parser = parser

    def _parent(self):
        self._parent_parser.add_argument('-l', '--loglevel', default='INFO',
                                         choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                                         help='provide logging level')
        self._parent_parser.add_argument('--version', dest='version', action='version', version=get_argus_version(),
                                         help='outputs the current program version')

    def _execute(self):
        execute_parser = self._subparsers.add_parser('execute', parents=[self._parent_parser])
        execute_parser.add_argument('config',
                                    help='configuration YML file path')
        execute_parser.add_argument('suite_dir',
                                    help='test folder containing suite YML files')
        execute_parser.add_argument('-v', '--validator', dest='validator',
                                    help='validator file path')
        execute_parser.add_argument('-s', '--suite', dest='suites',
                                    help='suites to run')
        execute_parser.add_argument('-t', '--tag', dest='tags',
                                    help='tags to run')
        execute_parser.add_argument('-i', '--input-dir', dest='input_dir',
                                    help='input file directory')
        execute_parser.add_argument('-o', '--output-dir', dest='output_dir',
                                    help='output file directory')
        execute_parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                                    help='simulate the execution without actually querying the webservices')

    def _stats(self):
        stats_parser = self._subparsers.add_parser('stats', parents=[self._parent_parser])
        stats_parser.add_argument('input', help='json file')


def create_logger(level):
    # Create logger
    logger = logging.getLogger('argus_logger')
    logger.setLevel(level)

    # Create console handler and set level
    ch = logging.StreamHandler()
    ch.setLevel(level)

    # Create formatter
    formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', '%Y/%m/%d %H:%M:%S')

    # Add formatter to console handler
    ch.setFormatter(formatter)

    # Add console handler to logger
    logger.addHandler(ch)

    return logger


def main():

    # Getting arguments
    cli = ArgusCLI()
    args = cli.parser.parse_args()

    # Setting up logger
    logger = create_logger(args.loglevel)
    logger.debug('Argus version: {}'.format(get_argus_version()))

    argus_config = ArgusConfiguration(
        args.config,
        validator=args.validator,
        suite_dir=args.suite_dir,
        suites=args.suites,
        tags=args.tags,
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        dry_run=args.dry_run
    ).get_config()

    client_generator = Argus(
        argus_config=argus_config
    )
    client_generator.execute()


if __name__ == '__main__':
    sys.exit(main())
