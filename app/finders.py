import os

from django.conf import settings
from django.contrib.staticfiles.finders import BaseFinder
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import FileSystemStorage


class StaticRootFinder(BaseFinder):
    """Serve files placed directly in the project static folder.

    That folder is STATIC_ROOT and is not committed. list() stays empty so
    collectstatic does not treat the folder as a second source.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = FileSystemStorage(location=settings.STATIC_ROOT)

    def check(self, **kwargs):
        return []

    def find(self, path, all=False, find_all=False):
        matches = []
        if settings.STATIC_ROOT:
            try:
                absolute = self.storage.path(path)
            except SuspiciousFileOperation:
                absolute = ""
            if absolute and os.path.isfile(absolute):
                matches.append(absolute)
        if all or find_all:
            return matches
        # An empty list, not None. Django's finder loop treats None as a hit.
        return matches[0] if matches else []

    def list(self, ignore_patterns):
        return []
