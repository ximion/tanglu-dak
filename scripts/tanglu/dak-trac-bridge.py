# Copyright (C) 2013 Matthias Klumpp <mak@debian.org>

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
#!/usr/bin/python

import os
import sys
import subprocess
from debian import deb822

# settings
TRAC_DIR = "/srv/bugs.tanglu.org"

class DakTracBridge:
    def __init__(self):
        self.tracComponents = self._getTracComponents ()

    def getArchiveSourcePackageInfo (self):
        p = subprocess.Popen( ["dak", "make-maintainers", "-a", "janus", "-s", "-p"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        resLines = ""
        while (True):
          retcode = p.poll ()
          line = p.stdout.readline ()
          resLines += line
          if (retcode is not None):
              break
        if p.returncode is not 0:
            raise Exception(resLines)

        rawPkgMaintLines = resLines.splitlines ()
        pkgMaintInfo = {}
        for cmpln in rawPkgMaintLines:
           tcomp = cmpln.strip ().split (" ", 1)
           if len (tcomp) > 1:
               pkgMaintInfo[tcomp[0].strip ()] = tcomp[1].strip ()

        return pkgMaintInfo

    def _getTracComponents (self):
        p = subprocess.Popen( ["trac-admin", TRAC_DIR, "component", "list"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        resLines = ""
        while (True):
          retcode = p.poll ()
          line = p.stdout.readline ()
          resLines += line
          if (retcode is not None):
              break
        if p.returncode is not 0:
            raise Exception(resLines)

        rawTracCmp = resLines.splitlines ()
        tracCmps = {}
        # NOTE: we keep the beginning comment and garbage in the components dict, as they are not harmful
        # for later processing
        for cmpln in rawTracCmp:
           tcomp = cmpln.strip ().split (" ", 1)
           if len (tcomp) > 1:
               tracCmps[tcomp[0].strip ()] = tcomp[1].strip ()

        return tracCmps

    def addTracComponent (self, name, user):
        print "[add] Adding new component '%s' and assigning to %s" % (name, user)
        try:
            output = subprocess.check_output (["trac-admin", TRAC_DIR, "component", "add", name, user.replace("'", "'\\''")])
        except subprocess.CalledProcessError as e:
            print e
            return False

        self.tracComponents[name] = user
        return True

    def chownTracComponent (self, name, user):
        print "[modify] Assigning component '%s' to %s" % (name, user)
        try:
            output = subprocess.check_output (["trac-admin", TRAC_DIR, "component", "chown", name, user.replace("'", "'\\''")])
        except subprocess.CalledProcessError as e:
            print e
            return False

        self.tracComponents[name] = user
        return True

    def refreshTracComponentList (self):
        # get some fresh data
        debSourceInfo = self.getArchiveSourcePackageInfo ()
        for spkg in debSourceInfo:
            pkg_name = spkg
            pkg_maint = debSourceInfo[spkg]
            if not pkg_name in self.tracComponents:
                self.addTracComponent (pkg_name, pkg_maint)
            elif not self.tracComponents[pkg_name] == pkg_maint:
                self.chownTracComponent (pkg_name, pkg_maint)
        # TODO: Maybe remove components as soon as they leave the maintained distribution?
        # (or better keep them for historic reasons?))

if __name__ == '__main__':
    daktrac = DakTracBridge ()
    daktrac.refreshTracComponentList ()

    print "Done."

