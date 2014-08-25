#!/usr/bin/env python
"""
Inserts appstream metadata per binary.
"""

# Copyright (C) 2014  Abhishek Bhattacharjee <abhishek.bhattacharjee11@gmail.com>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

#################################################################################

# the script is part of project under Google Summer of Code '14
# Project: AppStream/DEP-11 for the Debian Archive
# Mentor: Matthias Klumpp

#################################################################################

from daklib.dbconn import *

class DEP11Metadata():

    def __init__(self):
        self._session = DBConn().session()

    def insertdata(self,binid,yamldoc):
        d = {"bin_id":binid,"yaml_data":yamldoc}
        sql = "insert into bin_dep(binary_id,metadata) VALUES (:bin_id, :yaml_data)"
        self._session.execute(sql,d)

    def removedata(self,suitename):
        sql = """delete from bin_dep where binary_id in 
        (select distinct(b.id) from binaries b,override o,suite s where 
        b.package = o.package and o.suite = s.id and s.suite_name= :suitename)"""
        self._session.execute(sql,{"suitename" : suitename})
        self._session.commit()

    def close(self):
        self._session.close()

#for testing
if __name__ == "__main__":
    dobj = DEP11Metadata()
    dobj.insertdata(555,"test data test data")
    dobj._session.commit()
    dobj.close()
    #session = DBConn().session()
    
