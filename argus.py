#!/usr/bin/env python3

import sys

from argus.argus_cli import ArgusCLI
from argus.argus import Argus


def main():

    cli = ArgusCLI()
    args = cli.parser.parse_args()

    client_generator = Argus(args.suite_dir, args.config, args.output)
    client_generator.execute()


if __name__ == '__main__':
    sys.exit(main())
