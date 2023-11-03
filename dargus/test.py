class Test:
    def __init__(self, id_, tags=None, path=None, method=None, headers=None, async_=None, steps=None):
        self.id_ = id_
        self.tags = tags
        self.path = path
        self.method = method
        self.headers = headers if headers else {}
        self.async_ = async_
        self.steps = steps

    def __str__(self):
        return str(self.__dict__)
