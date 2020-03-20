#!/usr/bin/env python3

import sys
import argparse

from argus import Argus


class Opencga(Argus):
    def __init__(self, test_folder, config_yml, user):
        super().__init__(test_folder, config_yml)

        self.user = user


def _setup_argparse():
    desc = 'This script test automatically all defined tests'
    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument('test_folder', help='test folder with YML files')
    parser.add_argument('config_yml_fpath', help='config YML file path')
    parser.add_argument('user', help='OpenCGA user')
    args = parser.parse_args()
    return args


def main():
    # Getting arg parameters
    args = _setup_argparse()

    client_generator = Opencga(args.test_folder, args.config_yml_fpath,
                               args.user)
    client_generator.execute()


if __name__ == '__main__':
    sys.exit(main())
