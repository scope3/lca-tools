import os
import re
from py7zlib import Archive7z
from zipfile import ZipFile

_ext = re.compile('\.([^.]+)$')


def get_ext(fname):
    return _ext.search(fname).groups()[0].lower()


class Archive(object):

    @staticmethod
    def _access_7z(path):
        try:
            fp = open(path, 'rb')
            archive = Archive7z(fp)
        except:
            archive = False
        return archive

    @staticmethod
    def _access_zip(path):
        try:
            archive = ZipFile(path)
        except:
            archive = False
        return archive

    def __init__(self, path):
        """
        Create an Archive object from a path.  Basically encapsulates the compression algorithm and presents
        a common interface to client code:
        self.listfiles()
        self.countfiles()
        self.getfile(filename)

        writing archives is not presently supported.

        :param path:
        :return: an archive object
        """

        self.path = path
        self._numfiles = None

        if not os.path.exists(path):
            raise FileNotFoundError('path does not resolve')

        if os.path.isdir(path):
            print('Path points to a directory. Assuming expanded archive')
            self.path = os.path.abspath(path) + os.path.sep  # abs reference plus trailing slash
            self.compressed = False
            self._archive = None
            self.OK = os.access(path, os.R_OK)
            self.prefixes = [x[0][len(self.path):] for x in os.walk(path) if x[0] != path]
        else:
            self.compressed = True
            self.ext = get_ext(path)
            print('Found Extension: %s' % self.ext)
            self._archive = {
                '7z': self._access_7z,
                'zip': self._access_zip
            }[self.ext](path)
            self.OK = self._archive is not False
            if self.OK:
                self.prefixes = {
                    '7z': self._prefix_7z,
                    'zip': self._prefix_zip
                }[self.ext]()

    def _prefix_7z(self):
        s = set()
        for f in self._archive.files:
            s.add(os.path.split(f.filename)[0])
        return list(s)

    def _prefix_zip(self):
        s = set()
        for f in self._archive.namelist():
            s.add(os.path.split(f)[0])
        return list(s)

    def listfiles(self):
        """
        List files in the archive.
        :return:
        """
        if self.compressed:
            if self.ext == '7z':
                l = [q.filename for q in self._archive.files]
            elif self.ext == 'zip':
                l = [q for q in self._archive.namelist() if q[:-1] not in self.prefixes]
            else:
                l = []
        else:
            w = os.walk(self.path)
            l = []
            for i in w:
                if len(i[2]) > 0:
                    prefix = i[0][len(self.path):]
                    l.extend([os.path.join(prefix, z) for z in i[2]])
        self._numfiles = len(l)
        return l

    def countfiles(self):
        if self._numfiles is None:
            self.listfiles()
        return self._numfiles

    def readfile(self, fname):
        """
        Have to decide what this does. I think it should return the raw data- since there's no way to get a pointer
        to a file in a generic archive
        :param fname:
        :return:
        """
        if self.compressed:
            file = {
                '7z': lambda x: self._archive.getmember(x),
                'zip': lambda x: self._archive.open(x)
            }[self.ext](fname)
            if file is None:
                return file
            else:
                return file.read()

        else:
            file = open(os.path.join(self.path, fname), 'r')
            data = file.read()
            file.close()
            return data