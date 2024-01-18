class Suite:
    def __init__(self, id_, base_url=None, suite_variables=None, tests=None):
        self.id_ = id_
        self.base_url = base_url
        self.suite_variables = suite_variables
        self.tests = tests

    def __str__(self):
        return str(self.__dict__)
