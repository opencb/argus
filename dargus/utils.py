import re
import requests
import json
import json2html


def get_item_from_json(json_dict, field):
    for item in field.split('.'):
        items = list(filter(None, re.split(r'[\[\]]', item)))
        key, indexes = items[0], map(int, items[1:])
        json_dict = json_dict[key]
        if indexes:
            for i in indexes:
                json_dict = json_dict[i]
    return json_dict


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


def json_to_html(json_string):
    # Load the JSON string into a Python dictionary
    data = json.loads(json_string)

    # Function to recursively convert 'false' to False, 'true' to True, and 'null' to None
    def convert_bool_and_null(item):
        if isinstance(item, list):
            return [convert_bool_and_null(i) for i in item]
        elif isinstance(item, dict):
            return {k: convert_bool_and_null(v) for k, v in item.items()}
        elif isinstance(item, str):
            if item.lower() == 'false':
                return False
            elif item.lower() == 'true':
                return True
            elif item.lower() == 'null':
                return None
        return item

    # Apply the function to the data
    updated_data = convert_bool_and_null(data)

    # Convert the updated data back to JSON
    updated_json_string = json.dumps(updated_data, indent=2)

    # Print the updated JSON string
    scan_output = json2html.convert(json=updated_json_string)
    html_fpath = "./reports/output.html"
    with open(html_fpath, 'w') as html_fhand:
        html_fhand.write(str(scan_output))
