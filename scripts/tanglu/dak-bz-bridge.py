#!/usr/bin/python
# Copyright (C) 2013 Matthias Klumpp <mak@debian.org>
#
# Licensed under the GNU Lesser General Public License Version 3
#
# This library is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import subprocess
import psycopg2
import gzip
from ConfigParser import SafeConfigParser
from apt_pkg import TagFile, TagSection, version_compare

# settings
BUGZILLA_DIR = "/srv/bugs.tanglu.org"

class PackageInfo():
    def __init__(self, pkgname, pkgversion, dist, component):
        self.pkgname = pkgname.strip()
        self.version = pkgversion.strip()
        self.dist = dist
        self.component = component
        self.info = ""

class DakBzBridge:
    def __init__(self):
        parser = SafeConfigParser()
        parser.read(['/etc/jenkins/jenkins-dak.conf', 'jenkins-dak.conf'])
        self._archivePath = parser.get('Archive', 'path')
        dbname = parser.get('Bugzilla', 'dbname')
        user = parser.get('Bugzilla', 'user')
        password = parser.get('Bugzilla', 'password')

        try:
            self._conn = psycopg2.connect("dbname='%s' user='%s' host='localhost' password='%s'" % (dbname, user, password))
        except:
            raise Exception("I am unable to connect to the database")


    def _getArchiveSourcePackageInfo(self, dist, component):
        source_path = self._archivePath + "/dists/%s/%s/source/Sources.gz" % (dist, component)
        f = gzip.open(source_path, 'rb')
        tagf = TagFile (f)
        packageList = []
        for section in tagf:
            # don't even try to build source-only packages
            if section.get('Extra-Source-Only', 'no') == 'yes':
                continue

            pkgname = section['Package']
            archs_str = section['Architecture']
            binaries = section['Binary']
            pkgversion = section['Version']

            pkg = PackageInfo(pkgname, pkgversion, dist, component)

            pkg.info = ("Maintainer: <i>%s</i>\n<br>Co-Maintainers: <i>%s</i><br>\nVCS-Browser: %s" %
                        (section['Maintainer'], section.get('Uploaders', 'Nobody'), section.get('Vcs-Browser', '#')))

            packageList += [pkg]

        return packageList

    def _getBzComponentInfo(self):
        cur = self._conn.cursor()
        cur.execute("""SELECT name, description from components WHERE product_id='3'""")
        rows = cur.fetchall()
        components = {}
        for row in rows:
            components[row[0]] = row[1]
        return components

    def refreshBzTangluComponentList(self):
        # TODO: Adjust this to work with all active suites!
        cur = self._conn.cursor()
        for acmp in ["main", "contrib", "non-free"]:
            packages = self._getArchiveSourcePackageInfo("aequorea", acmp)
            components = self._getBzComponentInfo()
            for pkg in packages:
                desc = pkg.info
                if acmp == "non-free":
                    desc = "%s<br>\n<br>\nThis package is <strong>non-free</strong>." % (desc)
                elif acmp == "contrib":
                    desc = "%s<br>\n<br>\nThis package is part of <strong>contrib</strong>." % (desc)
                if pkg.pkgname not in components:
                    # insert the new package!
                    try:
                        cur.execute("""INSERT INTO components (name, product_id, initialowner, description, isactive) VALUES (%s, %s, %s, %s, %s);""",
                            (pkg.pkgname, 3, 2, desc, 1))
                    except:
                        print("Can't insert new package '%s' into Bz database." % (pkg.pkgname))
                else:
                    if components[pkg.pkgname] != desc:
                        # update package description
                        try:
                            cur.execute("""UPDATE components SET description=%s WHERE name=%s AND product_id=%s;""",
                                (desc, pkg.pkgname, 3))
                        except:
                            print("Can't update description for '%s' in Bz database." % (pkg.pkgname))
        self._conn.commit()


if __name__ == '__main__':
    dakbz = DakBzBridge()
    dakbz.refreshBzTangluComponentList()

    print("Done.")
