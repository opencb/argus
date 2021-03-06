#!/usr/bin/env python3

import argparse


class ArgusCLI:

    def __init__(self):
        self._parser = argparse.ArgumentParser(
            description='This program checks automatically all defined tests'
        )
        self.subparsers = self.parser.add_subparsers()

        self._execute()
        # self._stats()

    @property
    def parser(self):
        return self._parser

    @parser.setter
    def parser(self, parser):
        self._parser = parser

    def _execute(self):
        parser = self.subparsers.add_parser('execute')
        parser.add_argument('config',
                            help='configuration YML file path')
        parser.add_argument('suite_dir',
                            help='test folder containing suite YML files')
        parser.add_argument('-o', '--output',
                            help='output file path')
        # parser.add_argument('--suites',
        #                     help='suites to run; overrule config file')

    def _stats(self):
        parser = self.subparsers.add_parser('stats')
        parser.add_argument('input', help='json file')
