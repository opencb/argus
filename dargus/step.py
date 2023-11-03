class Step:
    def __init__(self, id_, path_params=None, query_params=None, body_params=None, validation=None):
        self.id_ = id_
        self.path_params = path_params
        self.query_params = query_params
        self.body_params = body_params
        self.validation = validation

    def __str__(self):
        return str(self.__dict__)
