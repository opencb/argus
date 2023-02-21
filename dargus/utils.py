import re
import requests


def get_item(json_dict, field):
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
