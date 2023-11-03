import re
import json
import json2html
import logging

LOGGER = logging.getLogger('argus_logger')


def get_item_from_json(json_dict, field):
    json_traceback = json_dict.copy()
    try:
        for item in field.split('.'):
            items = list(filter(None, re.split(r'[\[\]]', item)))
            key, indexes = items[0], map(int, items[1:])
            json_dict = json_dict[key]
            if indexes:
                for i in indexes:
                    json_dict = json_dict[i]
        return json_dict
    except IndexError as e:
        msg = 'Unable to retrieve field "{}" from JSON "{}". Reason: "{}".'
        LOGGER.error(msg.format(field, json_traceback, e))
        raise IndexError(e)


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
