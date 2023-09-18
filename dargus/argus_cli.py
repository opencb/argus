#!/usr/bin/env python3

import sys
import argparse
import logging

from dargus.argus import Argus
from dargus.argus_config import ArgusConfiguration


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

    def _execute(self):
        execute_parser = self._subparsers.add_parser('execute', parents=[self._parent_parser])
        execute_parser.add_argument('config',
                                    help='configuration YML file path')
        execute_parser.add_argument('suite_dir',
                                    help='test folder containing suite YML files')
        execute_parser.add_argument('-o', '--output',
                                    help='output file path')
        execute_parser.add_argument('-v', '--validator',
                                    help='validator file path')
        # execute_parser.add_argument('-u', '--username',
        #                     help='validator file path')
        # execute_parser.add_argument('-p', '--password',
        #                     help='validator file path')
        execute_parser.add_argument('-s', '--suites',
                                    help='suites to run')

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

    argus_config = ArgusConfiguration(
        args.config,
        validator=args.validator,
        # username=args.username,
        # password=args.password
        suites=args.suites
    ).get_config()

    client_generator = Argus(args.suite_dir, argus_config, args.output)
    client_generator.execute()


if __name__ == '__main__':
    sys.exit(main())
