#!/bin/bash

# Copyright (C) 2008,2010 Joerg Jaspert <joerg@debian.org>

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


set -e
set -u

# Load up some standard variables
export SCRIPTVARS=/srv/dak/config/tanglu/vars
. $SCRIPTVARS

IMPORTSUITE=${1:-"aequorea"}
BRITNEY=""

case "${IMPORTSUITE}" in
    aequorea)
        # What file we look at.
        INPUTFILE="/var/archive-kit/britney2/var/Heidi/set/current"
        DO_CHANGELOG="true"
        ;;
    *)
        echo "You are so wrong here that I can't even believe it. Sod off."
        exit 42
        ;;
esac

# Change to a known safe location
cd $masterdir

echo "Importing new data for ${IMPORTSUITE} into database"

if [ "x${DO_CHANGELOG}x" = "xtruex" ]; then
    rm -f ${ftpdir}/dists/${IMPORTSUITE}/ChangeLog
    BRITNEY=" --britney"
fi

# should be --set, but we use --add for safety now - should be changed later if testing has completed
dak control-suite --add ${IMPORTSUITE} ${BRITNEY} < ${INPUTFILE}

if [ "x${DO_CHANGELOG}x" = "xtruex" ]; then
    NOW=$(date "+%Y%m%d%H%M")
    cd ${ftpdir}/dists/${IMPORTSUITE}/
    mv ChangeLog ChangeLog.${NOW}
    ln -s ChangeLog.${NOW} ChangeLog
    find . -maxdepth 1 -mindepth 1 -type f -mmin +2880 -name 'ChangeLog.*' -delete
fi

#echo "Regenerating Packages/Sources files, be patient"
#dak generate-packages-sources2 -s ${IMPORTSUITE} >/dev/null

echo "Done"

exit 0
