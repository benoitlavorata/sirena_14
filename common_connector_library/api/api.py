import csv


class UnicodeDictReader(csv.DictReader):
    def __init__(self, csvfile, *args, **kwargs):
        """Allows to specify an additional keyword argument encoding which
        defaults to "utf-8"
        """
        self.encoding = kwargs.pop('encoding', 'utf-8')
        csv.DictReader.__init__(self, csvfile, *args, **kwargs)

    def __next__(self):
        rv = csv.DictReader.__next__()(self)
        return dict((
            (k, v.decode(self.encoding, 'ignore') if v else v) for k, v in rv.items()
        ))


class UnicodeDictWriter(csv.DictWriter):
    def __init__(self, csvfile, fieldnames, *args, **kwargs):
        """Allows to specify an additional keyword argument encoding which
        defaults to "utf-8"
        """
        self.encoding = kwargs.pop('encoding', 'utf-8')
        csv.DictWriter.__init__(self, csvfile, fieldnames, *args, **kwargs)

    def _dict_to_list(self, rowdict):
        rv = csv.DictWriter._dict_to_list(self, rowdict)
        return [(f.encode(self.encoding, 'ignore') if isinstance(f, str) else f) \
                for f in rv]


