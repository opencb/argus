class Suite:
    def __init__(self, id_, name=None, description=None, base_url=None, variables=None, tests=None, output_dir=None):
        self.id_ = id_
        self.name = name
        self.description = description
        self.base_url = base_url
        self.variables = variables
        self.tests = tests
        self.output_dir = output_dir

    def __str__(self):
        return str(self.__dict__)
