
"""
Added class and methods to exposes a dictionary's keys as class attributes and parse
the response dict.
"""

import re
from odoo.addons.amazon_ept.models import utils


def remove_namespace(xml):
    """
    will remove the space.
    """
    regex = re.compile(' xmlns(:ns2)?="[^"]+"|(ns2:)|(xml:)')
    return regex.sub('', xml)


class DictWrapper():
    """
    This is a simple class that exposes a dictionary's keys as class attributes, making for less
    typing when accessing dictionary values.
    """

    def __init__(self, xml, rootkey=None):
        """
        Override of __init__ to remove space from dict and prepare the response dict from
        xml data.
        """
        self.original = xml
        self._rootkey = rootkey
        self._mydict = utils.xml2dict().fromstring(remove_namespace(xml))
        self._response_dict = self._mydict.get(list(self._mydict.keys())[0],
                                               self._mydict)

    @property
    def parsed(self):
        """
        will parse th response dict.
        """
        if self._rootkey:
            return self._response_dict.get(self._rootkey)
        return self._response_dict
