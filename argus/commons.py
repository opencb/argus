from time import sleep
import requests


class AuthorisationError(Exception):
    def __init__(self, message):
        super(AuthorisationError, self).__init__(message)


class InvalidToken(Exception):
    def __init__(self, message):
        super(InvalidToken, self).__init__(message)


def _create_url(url, options):
    # URL without options
    url = url.split('?')[0]

    # Checking optional params
    if options is not None:
        opts = []
        for k, v in options.items():
            opts.append(k + '=' + str(v))
        if opts:
            url += '?' + '&'.join(opts)
    return url


def _get_options(url):
    opts = None if url.split('?') > 1 else url.split('?')[1].split('&')
    if opts is not None:
        return [i for i in map(lambda x: {x.split('=')[0]: x.split('=')[1]}, opts)][0]
    else:
        return None


def query(url, method='GET', headers=None, body=None):
    """Queries the REST service retrieving results until exhaustion or limit"""
    # HERE BE DRAGONS
    final_response = None

    # Setting up skip and limit default parameters
    call_skip = 0
    call_limit = 1000
    max_limit = None
    options = _get_options(url)
    if options is None:
        opts = {'skip': call_skip, 'limit': call_limit}
    else:
        opts = options.copy()  # Do not modify original data!
        if 'skip' not in opts:
            opts['skip'] = call_skip
        # If 'limit' is specified, a maximum of 'limit' results will be returned
        if 'limit' in opts:
            max_limit = int(opts['limit'])
        # Server must be always queried for results in groups of 1000
        opts['limit'] = call_limit

    # If some query has more than 'call_limit' results, the server will be
    # queried again to retrieve the next 'call_limit results'
    call = True
    current_query_id = None  # Current REST query
    current_id_list = None  # Current list of ids
    time_out_counter = 0  # Number of times a query is repeated due to time-out
    while call:
        # Check 'limit' parameter if there is a maximum limit of results
        if max_limit is not None and max_limit <= call_limit:
            opts['limit'] = max_limit

        # Retrieving url
        url = _create_url(url, opts)

        # Getting REST response
        if method.lower() == 'get':
            try:
                r = requests.get(url, headers=headers)
            except requests.exceptions.ConnectionError:
                sleep(1)
                r = requests.get(url, headers=headers)
        elif method.lower() == 'post':
            try:
                r = requests.post(url, json=body, headers=headers)
            except requests.exceptions.ConnectionError:
                sleep(1)
                r = requests.post(url, json=body, headers=headers)
        elif method.lower() == 'delete':
            try:
                r = requests.delete(url, headers=headers)
            except requests.exceptions.ConnectionError:
                sleep(1)
                r = requests.delete(url, headers=headers)
        else:
            raise NotImplementedError('method: ' + method + ' not implemented.')

        if r.status_code == 504:  # Gateway Time-out
            if time_out_counter == 99:
                msg = 'Server not responding in time'
                raise requests.ConnectionError(msg)
            time_out_counter += 1
            continue
        time_out_counter = 0

        if r.status_code == 401:
            raise InvalidToken(r.content)
        elif r.status_code == 403:
            raise AuthorisationError(r.content)
        elif r.status_code != 200:
            raise Exception(r.content)

        try:
            response = r.json()
        except ValueError:
            msg = 'Bad JSON format retrieved from server'
            raise ValueError(msg)

        # Setting up final_response
        if final_response is None:
            final_response = response
        # Concatenating results
        else:
            final_response['responses'][0]['results'] += response['responses'][0]['results']

        # Ending REST calling when there are no more results to retrieve
        if response['responses'][0]['numResults'] != call_limit:
            call = False

        # Skipping the first 'limit' results to retrieve the next ones
        opts['skip'] += call_limit

        # Subtracting the number of returned results from the maximum goal
        if max_limit is not None:
            max_limit -= call_limit
            # When 'limit' is 0 returns all the results. So, break the loop if 0
            if max_limit == 0:
                break

    return final_response
