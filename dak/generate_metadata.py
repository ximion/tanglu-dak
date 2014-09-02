#!/usr/bin/env python

"""
Takes a .deb file as an argument and reads the metadata from
diffrent sources such as the xml files in usr/share/appdata
and .desktop files in usr/share/application. Also created
screenshot cache and tarball of all the icons of packages
beloging to a given suite.
"""

# Copyright (C) 2014 Abhishek Bhattacharjee<abhishek.bhattacharjee11@gmail.com>

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

###########################################################################

# The script is part of project under Google Summer of Code '14
# Project: AppStream/DEP-11 for the Debian Archive
# Mentor: Matthias Klumpp

###########################################################################


from apt_inst import DebFile
from apt import debfile
import lxml.etree as et
import yaml
import re
import sys
import urllib
import glob
import sha
import tarfile
import shutil
import datetime
import os
import os.path
from PIL import Image
from subprocess import CalledProcessError
from check_appdata import appdata, findicon, clear_cached_dep11_data
from daklib.daksubprocess import call, check_call
from daklib.filewriter import ComponentDataFileWriter
from daklib.config import Config
from insert_dep import DEP11Metadata

###########################################################################
DEP11_VERSION = "0.6"
time_str = str(datetime.date.today())
logfile = None
dep11_header = {
    "File": "DEP-11",
    "Version": DEP11_VERSION
}
###########################################################################


def usage():
    print("""Usage: dak generate_metadata -s <suitename> [OPTION]
Generate DEP-11 metadata for the specified suite.

  -C, --clear-cache   use this option to clear stale DEP-11 cached data.
    """)


def enc_dec(val):
    '''
    Handles encoding decoding for localised values
    '''
    try:
        val = unicode(val, "UTF-8")
    except TypeError:
        # already unicode
        pass
    try:
        val = str(val)
    except UnicodeEncodeError:
        pass
    return val


class DEP11YAMLDumper(yaml.Dumper):
    '''
    Custom YAML dumper, to ensure resulting YAML file can be read by
    all parsers (even the Java one)
    '''
    def increase_indent(self, flow=False, indentless=False):
        return super(DEP11YAMLDumper, self).increase_indent(flow, False)


class ProvidedItemType(object):
    '''
    Types supported as publicly provided interfaces. Used as keys in
    the 'Provides' field
    '''
    BINARY = 'binaries'
    LIBRARY = 'libraries'
    MIMETYPE = 'mimetypes'
    DBUS = 'dbus'
    PYTHON_2 = 'python2'
    PYTHON_3 = 'python3'
    FIRMWARE = 'firmware'
    CODEC = 'codecs'


class ComponentData:
    '''
    Used to store the properties of component data. Used by MetaDataExtractor
    '''

    def __init__(self, suitename, component, binid, filename, filelist, pkg):
        '''
        Used to set the properties to None.
        '''
        self._suitename = suitename
        self._component = component
        self._filelist = filelist
        self._pkg = pkg
        self._binid = binid
        self._file = filename

        # properties
        self._compulsory_for_desktop = None
        self._ignore = False
        self._ID = None
        self._type = None
        self._name = dict()
        self._categories = None
        self._icon = None
        self._summary = dict()
        self._description = None
        self._screenshots = None
        self._keywords = None
        self._archs = None
        self._provides = dict()
        self._url = None
        self._project_license = None
        self._project_group = None

    @property
    def ignore(self):
        return self._ignore

    @ignore.setter
    def ignore(self, val):
        self._ignore = val

    @property
    def ID(self):
        return self._ID

    @ID.setter
    def ID(self, val):
        self._ID = val

    @property
    def kind(self):
        return self._type

    @kind.setter
    def kind(self, val):
        self._type = val

    @property
    def compulsory_for_desktop(self):
        return self._compulsory_for_desktop

    @compulsory_for_desktop.setter
    def compulsory_for_desktop(self, val):
        self._compulsory_for_desktop = val

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, val):
        self._name = val

    @property
    def categories(self):
        return self._categories

    @categories.setter
    def categories(self, val):
        self._categories = val

    @property
    def icon(self):
        return self._icon

    @icon.setter
    def icon(self, val):
        self._icon = val

    @property
    def summary(self):
        return self._summary

    @summary.setter
    def summary(self, val):
        self._summary = val

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, val):
        self._description = val

    @property
    def screenshots(self):
        return self._screenshots

    @screenshots.setter
    def screenshots(self, val):
        self._screenshots = val

    @property
    def keywords(self):
        return self._keywords

    @keywords.setter
    def keywords(self, val):
        self._keywords = val

    @property
    def archs(self):
        return self._archs

    @archs.setter
    def archs(self, val):
        self._archs = val

    @property
    def provides(self):
        return self._provides

    @provides.setter
    def provides(self, val):
        self._provides = val

    @property
    def url(self):
        return self._url

    @url.setter
    def url(self, val):
        self._url = val

    @property
    def project_license(self):
        return self._project_license

    @project_license.setter
    def project_license(self, val):
        self._project_license = val

    @property
    def project_group(self):
        return self._project_group

    @project_group.setter
    def project_group(self, val):
        self._project_group = val

    def add_provided_item(self, kind, value):
        if kind not in self.provides.keys():
            self.provides[kind] = list()
        self.provides[kind].append(value)

    def cleanup(self, dic):
        '''
        Remove cruft locale. And duplicates
        '''
        if dic.get('x-test'):
            dic.pop('x-test')
        if dic.get('xx'):
            dic.pop('xx')

        unlocalized = dic.get('C')
        if unlocalized:
            to_remove = []
            for k in dic.keys():
                if dic[k] == unlocalized and k != 'C':
                    dic.pop(k)

        return dic

    def serialize_to_dic(self):
        '''
        Return a dic with all the properties
        '''
        dic = {}
        dic['Packages'] = [self._pkg]

        if self.icon:
            # ignore if icon is not valid
            ext_allowed = ('.png', '.svg', '.ico', '.xcf', '.gif', '.svgz')
            if self.icon.endswith(ext_allowed):
                dic['Icon'] = {'cached': self.icon}
            else:
                self.ignore = True
                return None
        if self.kind == 'desktop-app' and not self.icon:
            self.ignore = True
            return None
        if self.ID:
            dic['ID'] = self.ID
        if self.kind:
            dic['Type'] = self.kind
        if self.name:
            dic['Name'] = self.cleanup(self.name)
        if self.summary:
            dic['Summary'] = self.cleanup(self.summary)
        if self.categories:
            dic['Categories'] = self.categories
        if self.description:
            dic['Description'] = self.description
        if self.keywords:
            dic['Keywords'] = self.keywords
        if self.screenshots:
            dic['Screenshots'] = self.screenshots
        if self.archs:
            dic['Architectures'] = self.archs
        if self.url:
            dic['Url'] = self.url
        if self.provides:
            dic['Provides'] = self.provides
        if self.project_license:
            dic['ProjectLicense'] = self.project_license
        if self.project_group:
            dic['ProjectGroup'] = self.project_group
        return dic


class MetaDataExtractor:
    '''
    Takes a deb file and extracts component metadata from it.
    '''

    def __init__(self, filename, xml_list=None, desk_list=None):
        '''
        Initialize the object with List of files.
        '''
        self._filename = filename
        self._deb = DebFile(filename)
        self._loxml = xml_list
        self._lodesk = desk_list

    def filelist(self):
        '''
        Returns a list of all files in a deb package
        '''
        filelist = debfile.DebPackage(self._filename).filelist
        return filelist

    def notcomment(self, line=None):
        '''
        checks whether a line is a comment on .desktop file.
        '''
        line = line.strip()
        if line:
            if line[0] == "#":
                return None
            else:
                # when there's a comment inline
                if "#" in line:
                    line = line[0:line.find("#")]
                    return line
        return line

    def find_id(self, dfile=None):
        '''
        Takes an absolute path as a string and
        returns the filename from the absolute path.
        '''
        li = dfile.split('/')
        return li.pop()

    def read_desktop(self, dcontent, compdata):
        '''
        Parses a .desktop file and sets ComponentData properties
        '''
        lines = dcontent.splitlines()
        for line in lines:
            line = self.notcomment(line)
            if line:
                # spliting into key-value pairs
                tray = line.split("=", 1)
                try:
                    key = tray[0].strip()
                    value = enc_dec(tray[1].strip())

                    if not value:
                        continue

                    # Should not specify encoding
                    if key.endswith('.UTF-8'):
                        key = key.strip('.UTF-8')

                    # Ignore the file if NoDisplay is true
                    if key == 'NoDisplay' and value == 'True':
                        compdata.ignore = True
                        break

                    if key == 'Type' and value != 'Application':
                        compdata.ignore = True
                    else:
                        compdata.kind = 'desktop-app'

                    if key.startswith('Name') and value:
                        if key == 'Name':
                            compdata.name['C'] = value
                        else:
                            compdata.name[key[5:-1]] = value
                        continue

                    if key == 'Categories':
                        value = value.split(';')
                        value.pop()
                        compdata.categories = value
                        continue

                    if key.startswith('Comment') and value:
                        if key == 'Comment':
                            compdata.summary['C'] = value
                        else:
                            compdata.summary[key[8:-1]] = value
                        continue

                    if key.startswith('Keywords'):
                        value = re.split(';|,', value)
                        if not value[-1]:
                            value.pop()
                        if key[8:] == '':
                            if compdata.keywords:
                                if set(value) not in \
                                   [set(val) for val in
                                        compdata.keywords.values()]:
                                    compdata.keywords.update(
                                        {'C': map(enc_dec, value)}
                                    )
                            else:
                                compdata.keywords = {
                                    'C': map(enc_dec, value)
                                }
                        else:
                            if compdata.keywords:
                                if set(value) not in \
                                   [set(val) for val in
                                        compdata.keywords.values()]:
                                    compdata.keywords.update(
                                        {key[9:-1]: map(enc_dec, value)}
                                    )
                            else:
                                compdata.keywords = {
                                    key[9:-1]: map(enc_dec, value)
                                }
                        continue

                    if key == 'MimeType':
                        value = value.split(';')
                        if len(value) > 1:
                            value.pop()
                        for val in value:
                            compdata.add_provided_item(
                                ProvidedItemType.MIMETYPE, val
                            )
                        continue

                    if 'Architectures' in key:
                        val_list = value.split(',')
                        compdata.archs = val_list
                        continue

                    if key == 'Icon':
                        compdata.icon = value

                except:
                    pass

    def neat(self, s):
        '''
        Utility for do_description
        '''
        s = s.strip()
        s = " ".join(s.split())
        return s

    def parse_description_tag(self, subs):
        '''
        Handles the description tag
        '''
        dic = {}
        for usubs in subs:
            attr_dic = usubs.attrib
            if attr_dic:
                for v in attr_dic.values():
                    key = v
            else:
                key = 'C'

            if usubs.tag == 'p':
                if dic.get(key):
                    dic[key] += "<p>%s</p>" % self.neat(enc_dec(usubs.text))
                else:
                    dic[key] = "<p>%s</p>" % self.neat(enc_dec(usubs.text))

            if usubs.tag == 'ul' or usubs.tag == 'ol':
                for k in dic.keys():
                    dic[k] += "<%s>" % usubs.tag

                for u_usubs in usubs:
                    attr_dic = u_usubs.attrib
                    if attr_dic:
                        for v in attr_dic.values():
                            key = v
                    else:
                        key = 'C'

                    if u_usubs.tag == 'li':
                        if dic.get(key):
                            dic[key] += "<li>%s</li>" % \
                                        self.neat(enc_dec(u_usubs.text))
                        else:
                            dic[key] = "<%s><li>%s</li>" % \
                                       (usubs.tag, self.neat(enc_dec
                                                             (u_usubs.text)))

                for k in dic.keys():
                    dic[k] += "</%s>" % usubs.tag
        return dic

    def parse_screenshots_tag(self, subs):
        '''
        Handles screenshots.Caption source-image etc.
        '''
        shots = []
        for usubs in subs:
            # for one screeshot tag
            if usubs.tag == 'screenshot':
                screenshot = {}
                attr_dic = usubs.attrib
                if attr_dic.get('type'):
                    if attr_dic['type'] == 'default':
                        screenshot['default'] = True
                # in case of old styled xmls
                url = usubs.text.strip()
                if url:
                    screenshot['source-image'] = {'url': url}
                    shots.append(screenshot)
                    continue

                # else look for captions and image tag
                for tags in usubs:
                    if tags.tag == 'caption':
                        # for localisation
                        attr_dic = tags.attrib
                        if attr_dic:
                            for v in attr_dic.values():
                                key = v
                        else:
                            key = 'C'

                        if screenshot.get('caption'):
                            screenshot['caption'][key] = enc_dec(tags.text)
                        else:
                            screenshot['caption'] = {key: enc_dec(tags.text)}
                    if tags.tag == 'image':
                        screenshot['source-image'] = {'url': tags.text}

                shots.append(screenshot)

        return shots

    def read_xml(self, xml_content, compdata):
        '''
        Reads the appdata from the xml file in usr/share/appdata.
        Sets ComponentData properties
        '''
        root = et.fromstring(xml_content)
        for key, val in root.attrib.iteritems():
            if key == 'type':
                if root.attrib['type'] == 'desktop':
                    compdata.kind = 'desktop-app'
                else:
                    # for other components like addon,codec, inputmethod etc
                    compdata.kind = root.attrib['type']

        for subs in root:
            if subs.tag == 'id':
                compdata.ID = subs.text

            if subs.tag == "description":
                desc = self.parse_description_tag(subs)
                compdata.description = desc

            if subs.tag == "screenshots":
                screen = self.parse_screenshots_tag(subs)
                compdata.screenshots = screen

            if subs.tag == "provides":
                for bins in subs:
                    if bins.tag == "binary":
                        compdata.add_provided_item(
                            ProvidedItemType.BINARY, bins.text
                        )
                    if bins.tag == 'library':
                        compdata.add_provided_item(
                            ProvidedItemType.LIBRARY, bins.text
                        )
                    if bins.tag == 'dbus':
                        compdata.add_provided_item(
                            ProvidedItemType.DBUS, bins.text
                        )
                    if bins.tag == 'firmware':
                        compdata.add_provided_item(
                            ProvidedItemType.FIRMWARE, bins.text
                        )
                    if bins.tag == 'python2':
                        compdata.add_provided_item(
                            ProvidedItemType.PYTHON_2, bins.text
                        )
                    if bins.tag == 'python3':
                        compdata.add_provided_item(
                            ProvidedItemType.PYTHON_3, bins.text
                        )
                    if bins.tag == 'codec':
                        compdata.add_provided_item(
                            ProvidedItemType.CODEC, bins.text
                        )

            if subs.tag == "url":
                if compdata.url:
                    compdata.url.update({subs.attrib['type']: subs.text})
                else:
                    compdata.url = {subs.attrib['type']: subs.text}

            if subs.tag == "project_license":
                compdata.project_license = subs.text

            if subs.tag == "project_group":
                compdata.project_group = subs.text

            if subs.tag == "CompulsoryForDesktop":
                if compdata.compulsory_for_desktop:
                    compdata.compulsory_for_desktop.append(subs.text)
                else:
                    compdata.compulsory_for_desktop = [subs.text]

    def read_metadata(self, suitename, component, binid, filelist, pkg):
        '''
        Reads the metadata from the xml file and the desktop files.
        And returns a list of ComponentData objects.
        '''
        component_list = []
        # Reading xml files and associated .desktop
        if self._loxml:
            for meta_file in self._loxml:
                compdata = ComponentData(suitename, component, binid,
                                         self._filename, filelist, pkg)
                xml_content = str(self._deb.data.extractdata(meta_file))
                self.read_xml(xml_content, compdata)
                # Reads the desktop files associated with the xml file
                if compdata.ID:
                    if('.desktop' in compdata.ID) and self._lodesk:
                        for dfile in self._lodesk:
                            # for desktop file matching the ID
                            if compdata.ID in dfile:
                                dcontent = self._deb.data.extractdata(dfile)
                                self.read_desktop(dcontent, compdata)
                                # overwriting the Type field of .desktop by xml
                                self._lodesk.remove(dfile)

                    if not compdata.ignore:
                        component_list.append(compdata)
                else:
                    # ignore if ID is not present for an xml, it is not valid!
                    compdata.ignore = True

        else:
            print('xml list is empty for the deb ' + self._filename)

        # Reading the desktop files other than the file which matches
        # the id in the xml file
        if self._lodesk:
            for dfile in self._lodesk:
                compdata = ComponentData(suitename, component, binid,
                                         self._filename, filelist, pkg)
                dcontent = self._deb.data.extractdata(dfile)
                self.read_desktop(dcontent, compdata)
                if not compdata.ignore:
                    compdata.ID = self.find_id(dfile)
                    component_list.append(compdata)
        else:
            print('desktop list is empty for the deb ' + self._filename)

        return component_list


class ContentGenerator:
    '''
    Takes a ComponentData object.And writes the metadat into YAML format
    Stores screenshot and icons.
    '''
    def __init__(self, compdata):
        '''
        List contains componendata of a archtype of a component
        '''
        self._cdata = compdata

    def write_meta(self, dic, ofile, dep11):
        '''
        Saves Appstream metadata in yaml format and also invokes
        the fetch_store function.
        '''
        metadata = yaml.dump(dic, Dumper=DEP11YAMLDumper,
                             default_flow_style=False, explicit_start=True,
                             explicit_end=False, width=100, indent=2,
                             allow_unicode=True)
        ofile.write(metadata)
        dep11.insertdata(self._cdata._binid, metadata)
        dep11._session.commit()

    def make_url(self, path):
        '''
        Take an absolute path and convert into valid url
        '''
        check = path.find('/export/')
        # this would change later
        url = "http://ftp.debian.org%s" % path[check:]
        return url

    def scale_screenshots(self, imgsrc, path):
        '''
        scale images in three sets of two-dimensions
        (752x423 624x351 and 112x63)
        '''
        thumbnails = []
        name = imgsrc.split('/').pop()
        sizes = ['752x423', '624x351', '112x63']
        for size in sizes:
            wd, ht = size.split('x')
            img = Image.open(imgsrc)
            newimg = img.resize((int(wd), int(ht)), Image.ANTIALIAS)
            newpath = path+size+"/"
            if not os.path.exists(newpath):
                os.makedirs(os.path.dirname(newpath))
            newimg.save(newpath+name)
            url = self.make_url(newpath+name)
            thumbnails.append({'url': url, 'height': int(ht),
                               'width': int(wd)})

        return thumbnails

    def fetch_screenshots(self, values):
        '''
        Fetches screenshots from the given url and
        stores it in png format.
        '''
        if self._cdata.screenshots:
            success = []
            shots = []
            for shot in self._cdata.screenshots:
                try:
                    image = urllib.urlopen(shot['source-image']['url']).read()
                    has = sha.new(image)
                    hd = has.hexdigest()
                    template = (Config()["Dir::MetaInfo"] +
                                "%(suite)s/%(component)s/")
                    path = template % values
                    path = "%s%s-%s/screenshots/" % \
                           (path, self._cdata._pkg, str(self._cdata._binid))
                    if not os.path.exists(path):
                        os.makedirs(os.path.dirname(path + "source/"))
                    f = open('%ssource/screenshot-%s.png' % (path, hd), 'wb')
                    f.write(image)
                    f.close()
                    img = Image.open('%ssource/screenshot-%s.png' % (path, hd))
                    wd, ht = img.size
                    shot['source-image']['width'] = wd
                    shot['source-image']['height'] = ht
                    shot['source-image']['url'] = self.make_url(
                        '%ssource/screenshot-%s.png' % (path, hd))
                    img.close()
                    # scale_screenshots will return a list of
                    # dicts with {height,width,url}
                    shot['thumbnails'] = self.scale_screenshots(
                        '%ssource/screenshot-%s.png' % (path, hd), path)
                    shots.append(shot)
                    success.append(True)
                    print("Screenshot saved...")
                except:
                    success.append(False)

            self._cdata.screenshots = shots
            return any(success)

        # don't ignore metadata if screenshots itself is not present
        return True

    def save_icon(self, icon, filepath, values):
        '''
        Extracts the icon from the deb package and stores it.
        '''
        template = Config()["Dir::MetaInfo"]+"%(suite)s/%(component)s/"
        path = template % values
        path = "%s%s-%s/icons/" % \
               (path, self._cdata._pkg, str(self._cdata._binid))
        icon_name = icon.split('/').pop()
        self._cdata.icon = icon_name
        # filepath is checked because icon can reside in another binary
        # eg amarok's icon is in amarok-data
        if os.path.exists(filepath):
            icon_data = DebFile(filepath).data.extractdata(icon)
            if icon_data:
                if not os.path.exists(path):
                    os.makedirs(os.path.dirname(path))
                f = open("{0}/{1}".format(path, icon_name), "wb")
                f.write(icon_data)
                f.close()
                print("Saved icon....")
                return True
        return False

    def fetch_icon(self, values):
        '''
        Searches for icon if aboslute path to an icon
        is not given. Component with invalid icons are ignored
        '''
        if self._cdata.icon:
            icon = self._cdata.icon
            self._cdata.icon = icon.split('/').pop()
            if icon.endswith('.xpm') or icon.endswith('.tiff'):
                self._cdata.ignore = True
                return False

            if icon[1:] in self._cdata._filelist:
                return self.save_icon(icon[1:], self._cdata._file, values)

            else:
                ext_allowed = ('.png', '.svg', '.ico', '.xcf', '.gif', '.svgz')
                for path in self._cdata._filelist:
                    if path.endswith(ext_allowed):
                        if 'pixmaps' in path or 'icons' in path:
                            return self.save_icon(
                                path, self._cdata._file, values)

                ficon = findicon(self._cdata._pkg, icon, self._cdata._binid)
                flist = ficon.queryicon()
                ficon.close()

                if flist:
                    filepath = (Config()["Dir::Pool"] +
                                self._cdata._component + '/' + flist[1])
                    return self.save_icon(flist[0], filepath, values)
                return False
        # keep metadata if Icon self itself is not present
        return True


class MetadataPool:
    '''
    Keeps a pool of component metadata per arch per component
    '''

    def __init__(self, values):
        '''
        Sets the archname of the metadata pool.
        '''
        self._values = values
        self._list = []

    def append_compdata(self, compdatalist):
        '''
        makes a list of all the componentdata objects in a arch pool
        '''
        self._list = self._list + compdatalist

    def saver(self):
        """
        Writes yaml doc, saves metadata in db and stores icons
        and screenshots
        """
        writer = ComponentDataFileWriter(**self._values)
        head_string = yaml.dump(dep11_header, Dumper=DEP11YAMLDumper,
                                default_flow_style=False, explicit_start=True,
                                explicit_end=False, width=100, indent=2)
        ofile = writer.open()
        ofile.write(head_string)
        dep11 = DEP11Metadata()
        for cdata in self._list:
            cg = ContentGenerator(cdata)
            screen_bool = cg.fetch_screenshots(self._values)
            icon_bool = cg.fetch_icon(self._values)
            dic = cg._cdata.serialize_to_dic()
            if (screen_bool or icon_bool) and not cg._cdata.ignore:
                cg.write_meta(dic, ofile, dep11)
        writer.close()
        dep11.close()

##############################################################################


def make_icon_tar(suitename, component):
    '''
     Icons-%(component).tar.gz of each Component.
    '''

    location = "%s%s/%s/*/icons/" % \
               (Config()["Dir::MetaInfo"], suitename, component)
    tar_location = "%sdists/%s/%s/" % \
                   (Config()["Dir::Root"], suitename, component)
    copy_location = tar_location + "Icons/"

    if not os.path.exists(copy_location):
        os.makedirs(os.path.dirname(copy_location))

    for filename in glob.glob(location+"*.*"):
        icon_name = filename.split('/').pop()
        img = open(filename, "rb")
        img_data = img.read()
        img.close()
        img_copy = open(copy_location+icon_name, "wb")
        img_copy.write(img_data)
        img_copy.close()

    tar = tarfile.open("%sIcons-%s.tar.gz" % (tar_location, component), "w:gz")
    tar.add(copy_location, arcname="Icons-%s" % component)
    tar.close()
    shutil.rmtree(copy_location)


def loop_per_component(component, suitename=None):
    '''
    Run by main to loop for different component and architecture.
    '''
    path = Config()["Dir::Pool"]

    print("Reading data...")
    datalist = appdata()
    # datalist.find_desktop(component=component,suitename=suitename)
    # datalist.find_xml(component=component,suitename=suitename)
    datalist.find_meta_files(component=component, suitename=suitename)
    datalist.close()
    print("data read complete")

    desk_dic = datalist._deskdic
    xml_dic = datalist._xmldic

    info_dic = datalist._idlist
    pkg_list = datalist._pkglist

    for arch in datalist.arch_deblist.iterkeys():
        values = {
            'suite': suitename,
            'component': component,
            'architecture': arch
        }
        pool = MetadataPool(values)

        for key in datalist.arch_deblist[arch]:
            print("Processing deb: %s" % (key))
            xmlfiles = []
            deskfiles = []
            if xml_dic:
                xmlfiles = xml_dic.get(key)
            if desk_dic:
                deskfiles = desk_dic.get(key)

            # loop over all_dic to find metadata of all the debian packages
            if os.path.exists(path+key):
                mde = MetaDataExtractor(path+key, xmlfiles, deskfiles)
                filelist = mde.filelist()
                cd_list = mde.read_metadata(suitename, component,
                                            str(info_dic[key]),
                                            filelist, pkg_list[key])
                pool.append_compdata(cd_list)
            else:
                print('Invalid path %s' % (path+key))

        # Save metadata of all binaries of the Component-arch
        pool.saver()

    make_icon_tar(suitename, component)
    print("Done with component ", component)


def main():
    if len(sys.argv) < 2:
        usage()
        return
    args = sys.argv

    # sanity checks
    if '-s' in args:
        i = args.index('-s')
        suitename = args[i+1]
        if suitename == '-C' or suitename == '--clear-cache':
            usage()
            return
    else:
        usage()
        return

    if '-C' in args or '--clear-cache' in args:
        clear_cached_dep11_data(suitename)

    global logfile
    global dep11_header
    logfile = open("{0}genmeta-{1}.txt".format(
        Config()["Dir::log"], time_str), 'w')
    dep11_header["Origin"] = suitename
    comp_list = ('contrib',)
    for component in comp_list:
        loop_per_component(component, suitename)

    logfile.close()

if __name__ == "__main__":
    main()
