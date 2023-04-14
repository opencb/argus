from datetime import datetime


class ValidationResult:
    def __init__(self, current, url, response, validation, headers=None):
        self.suite_id = current.id_
        self.test_id = current.tests[0].id_
        self.task_id = current.tests[0].tasks[0].id_
        self.url = url
        self.validation = validation
        self.headers = headers
        self.tags = current.tests[0].tags
        self.method = current.tests[0].method
        self.async_ = current.tests[0].async_
        self.time = response.elapsed.total_seconds()
        self.params = current.tests[0].tasks[0].query_params
        self.status_code = response.status_code
        self.status = all([v['result'] for v in validation])
        self.events = None
        self.version = None
        self.timestamp = int(datetime.now().strftime('%Y%m%d%H%M%S'))

    def to_json(self):
        return self.__dict__
