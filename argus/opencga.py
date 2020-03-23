#!/usr/bin/env python3

import sys
import argparse

from argus import Argus
from opencga_validator import OpencgaValidator


class Opencga(Argus):
    def __init__(self, test_folder, config_yml):
        super().__init__(test_folder, config_yml)

        self.validator = OpencgaValidator(config=self.config)


def _setup_argparse():
    desc = 'This script test automatically all defined tests'
    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument('test_folder', help='test folder with YML files')
    parser.add_argument('config_yml_fpath', help='config YML file path')
    args = parser.parse_args()
    return args


def main():
    # Getting arg parameters
    args = _setup_argparse()

    client_generator = Opencga(args.test_folder, args.config_yml_fpath)
    client_generator.execute()


if __name__ == '__main__':
    sys.exit(main())
