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
    # TODO
    # print('URL={}; HEADERS={}; BODY={};\n'.format(url, headers, body))
    if method.lower() == 'get':
        response = requests.get(url, headers=headers)
    elif method.lower() == 'post':
        response = requests.post(url, json=body, headers=headers)
    else:
        msg = 'Method "' + method + '" not implemented.'
        raise NotImplementedError(msg)
    return response
