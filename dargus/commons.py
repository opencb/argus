from time import sleep
import requests


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
    if method.lower() == 'get':
        response = requests.get(url, headers=headers)
    elif method.lower() == 'post':
        response = requests.post(url, json=body, headers=headers)
    else:
        msg = 'Method "' + method + '" not implemented.'
        raise NotImplementedError(msg)
    return response
