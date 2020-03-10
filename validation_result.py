class ValidationResult:
    def __init__(self, id_, url=None, time=None, headers=None,
                 api_version=None, status_code=None, num_results=None,
                 errors=None):
        self.id = id_
        self.url = url
        self.headers = headers
        self.time = time
        self.status_code = status_code
        self.api_version = api_version
        self.num_results = num_results
        self.errors = errors

    def to_json(self):
        return self.__dict__
