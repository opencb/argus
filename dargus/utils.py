import os
import re
import json
import json2html
import logging
import random
import string
import requests
from importlib.metadata import version

import pandas as pd
import seaborn as sns
import scipy.stats as stats
import matplotlib.pyplot as plt

LOGGER = logging.getLogger('argus_logger')


def get_item_from_json(json_dict, field):
    json_traceback = json_dict.copy()
    try:
        if field:
            for item in field.split('.'):
                items = list(filter(None, re.split(r'[\[\]]', item)))
                key, indexes = items[0], map(int, items[1:])
                json_dict = json_dict[key]
                if indexes:
                    for i in indexes:
                        json_dict = json_dict[i]
        return json_dict
    except (IndexError, KeyError) as e:
        msg = 'Unable to retrieve field "{}" from JSON "{}". Reason: "{}: {}".'
        LOGGER.error(msg.format(field, json_traceback, type(e).__name__, e))
        raise e


def dot2python(field):
    z = []
    for i, item in enumerate(field.split('.')):
        if i == 0:
            z.append(item)
        else:
            item_split = item.split('[')
            if item_split[0][-1] == ')':  # Support for type casting "int(v.firsts[0].second)"
                key = '["{}"])'.format(item_split[0].rstrip(')'))
            else:
                key = '["{}"]'.format(item_split[0])
            z.append(key)
            if len(item_split) > 1:
                z.append(item[len(item_split[0]):])
    return ''.join(z)


def create_url(url, path_params, query_params):
    if path_params is not None:
        try:
            url = url.format(**path_params)
        except KeyError as e:
            msg = 'Missing field in pathParams ({})'
            raise ValueError(msg.format(e))
    if query_params is not None:
        url += '?' + '&'.join(['{}={}'.format(k, query_params[k])
                               for k in query_params])
    return url


def query(url, method='GET', headers=None, body=None):
    if not method:
        method = 'get'
    if method.lower() == 'get':
        response = requests.get(url, headers=headers)
    elif method.lower() == 'post':
        response = requests.post(url, json=body, headers=headers)
    elif method.lower() == 'delete':
        response = requests.delete(url, json=body, headers=headers)
    else:
        msg = 'Method "' + method + '" not implemented.'
        raise NotImplementedError(msg)
    return response


def num_compare(a, b, operator):
    a, b = float(a), float(b)
    if operator in ['=', '==', 'eq']:
        return a == b
    elif operator in ['!=', 'ne']:
        return a != b
    elif operator in ['>', 'gt']:
        return a > b
    elif operator in ['>=', 'ge']:
        return a >= b
    elif operator in ['<', 'lt']:
        return a < b
    elif operator in ['<=', 'le']:
        return a <= b


def convert_bool_and_null(item):
    """Function to recursively convert 'false' to False, 'true' to True, and 'null' to None"""
    if isinstance(item, list):
        return [convert_bool_and_null(i) for i in item]
    elif isinstance(item, dict):
        return {k: convert_bool_and_null(v) for k, v in item.items()}
    elif isinstance(item, str):
        if item.lower() == 'false':
            return 'False'
        elif item.lower() == 'true':
            return 'True'
        elif item.lower() == 'null':
            return 'None'
    return item


def json_to_html(json_string):
    # Convert bool and null values
    updated_json_string = json.dumps(convert_bool_and_null(json_string), indent=2)

    # Convert JSON to HTML
    out_html = json2html.json2html.convert(json=updated_json_string)
    return out_html


def get_argus_version():
    parent_folder = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if 'pyproject.toml' in [f for f in os.listdir(parent_folder)]:
        for line in open(os.path.join(parent_folder, 'pyproject.toml'), 'r'):
            if line.startswith('version'):
                return line.split('=')[1].replace('"', '').strip()
    else:
        return version('dargus')


def replace_random_vars(lines):
    new_lines = []
    for line in lines:
        findings = re.findall('.*?(\${(.*?\((.*?)\))}).*?', line)
        if not findings:
            new_lines.append(line)
        else:
            for finding in findings:
                template, func, args = finding
                if func.startswith('RANDOM'):
                    n = int(args) if args else 6
                    random_value = ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))
                    line = line.replace(template, random_value, 1)
                elif func.startswith('RANDINT'):
                    a, b = map(int, re.sub(re.compile(r'\s+'), '', args).split(','))
                    random_value = str(random.randint(a, b))
                    line = line.replace(template, random_value, 1)
                elif func.startswith('RANDCHOICE'):
                    choices = re.sub(re.compile(r'\s+'), '', args).split(',')
                    random_value = random.choice(choices)
                    line = line.replace(template, random_value, 1)
                else:
                    raise ValueError('Random variable function "{}" not supported'.format(template))
            new_lines.append(line)
    return new_lines


def replace_variables(item, variables):
    if item is None or isinstance(item, bool) or isinstance(item, int) or isinstance(item, float):
        return item
    if isinstance(item, list):
        for i, list_item in enumerate(item):
            item[i] = replace_variables(list_item, variables)
    elif isinstance(item, dict):
        for k in item:
            item[k] = replace_variables(item[k], variables)
    else:
        for variable in variables:
            # Format: to include a brace character in the literal text, it can be escaped by doubling: {{ and }}
            item = item.replace('${{{var}}}'.format(var=variable), variables[variable])
    return item


def plot_regression_line(input_fpath, output_fpath, x=1, y=2, sep='\t', header=True):

    # Reading inpiut data
    header = 0 if header else None
    input_data = pd.read_csv(input_fpath, sep=sep, header=header)

    # Getting data points
    x = input_data.columns[x]
    y = input_data.columns[y]

    # Creating plot
    plot = sns.regplot(x=x, y=y, data=input_data)

    # Calculating slope and intercept of regression equation
    slope, intercept, r, p, sterr = stats.linregress(x=plot.get_lines()[0].get_xdata(),
                                                     y=plot.get_lines()[0].get_ydata())

    # Adding regression equation and r2 to plot
    txt = 'y = {} + {}x\nr2 = {}'.format(round(intercept, 3), round(slope, 3), round(r, 3))
    plot.set_title('{}'.format(txt))

    # Saving plot
    if output_fpath.endswith('.png'):
        plt.savefig(output_fpath)
    elif output_fpath.endswith('.jpg'):
        plt.savefig(output_fpath, dpi=300)
    elif output_fpath.endswith('.svg'):
        plt.savefig(output_fpath, format='svg')
    elif output_fpath.endswith('.pdf'):
        plt.savefig(output_fpath, format='pdf')
    else:
        msg = 'Format for file {} not recognised. Please use one of the following extensions: [.png|.jpg|.svg|.pdf]'
        raise ValueError(msg.format(output_fpath))

    return r
