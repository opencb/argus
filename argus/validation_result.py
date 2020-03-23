from datetime import datetime


class ValidationResult:
    def __init__(self, test_id, task_id, url=None, tags=None, method=None,
                 async_=None, time=None, params=None, headers=None,
                 status_code=None, num_results=None, num_errors=None,
                 events=None, validation=None, status=None, version=None):
        self.test_id = test_id
        self.task_id = task_id
        self.url = url
        self.headers = headers
        self.tags = tags
        self.method = method
        self.async_ = async_
        self.time = time
        self.params = params
        self.status_code = status_code
        self.num_results = num_results
        self.num_errors = num_errors
        self.events = events
        self.validation = validation
        self.status = status
        self.version = version
        self.timestamp = int(datetime.now().strftime('%Y%m%d%H%M%S'))

    def to_json(self):
        return self.__dict__
