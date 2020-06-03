# -*- coding: utf-8 -*-
"""
/***************************************************************************
 MapTiler
                                 A QGIS plugin
 Show MapTiler cloud maps.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2020-04-02
        git sha              : $Format:%H$
        copyright            : (C) 2020 by MapTiler AG
        email                : sales@maptiler.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os.path
import json
import re

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt, QModelIndex, QMetaObject
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QDockWidget, QCompleter, QLineEdit
from qgis.core import *

from .browser_root_collection import DataItemProvider
from .geocoder import MapTilerGeocoder


class MapTiler:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        self.proj = QgsProject.instance()

        # Save reference to the QGIS interface
        self.iface = iface

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'MapTiler_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&MapTiler')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'MapTiler')
        self.toolbar.setObjectName(u'MapTiler')

        # init QCompleter
        self.completer = QCompleter([])
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setMaxVisibleItems(30)
        self.completer.setModelSorting(QCompleter.UnsortedModel)
        self.completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.completer.activated[QModelIndex].connect(self.on_result_clicked)

        # init LineEdit of searchword
        self.search_line_edit = QLineEdit()
        self.search_line_edit.setPlaceholderText('MapTiler Geocoding API')
        self.search_line_edit.setMaximumWidth(300)
        self.search_line_edit.setClearButtonEnabled(True)
        self.search_line_edit.setCompleter(self.completer)
        self.search_line_edit.textEdited.connect(self.on_searchword_edited)
        self.search_line_edit.returnPressed.connect(
            self.on_searchword_returned)
        self.toolbar.addWidget(self.search_line_edit)

        self.pluginIsActive = False

        self._default_copyright = QgsProject.instance(
        ).readEntry("CopyrightLabel", "/Label")[0]

    # noinspection PyMethodMayBeStatic

    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('MapTiler', message)

    def initGui(self):
        # add MapTiler Collection to Browser
        self.dip = DataItemProvider()
        QgsApplication.instance().dataItemProviderRegistry().addProvider(self.dip)

        self._activate_copyrights()

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        # remove MapTiler Collection to Browser
        QgsApplication.instance().dataItemProviderRegistry().removeProvider(self.dip)
        self.dip = None

        # remove the toolbar
        del self.toolbar

        self._deactivate_copyrights()

    def _activate_copyrights(self):
        self.iface.layerTreeView().clicked.connect(
            self._write_copyright_entries)
        self.iface.layerTreeView().currentLayerChanged.connect(
            self._write_copyright_entries)
        self.proj.layersAdded.connect(self._write_copyright_entries)
        self.proj.layersRemoved.connect(self._write_copyright_entries)

    def _deactivate_copyrights(self):
        self.iface.layerTreeView().clicked.disconnect(
            self._write_copyright_entries)
        self.iface.layerTreeView().currentLayerChanged.disconnect(
            self._write_copyright_entries)
        self.proj.layersAdded.disconnect(self._write_copyright_entries)
        self.proj.layersRemoved.disconnect(self._write_copyright_entries)
        QgsProject.instance().writeEntry(
            "CopyrightLabel", "/Label", self._default_copyright)
        QgsProject.instance().writeEntry("CopyrightLabel", "/Enabled", False)
        QMetaObject.invokeMethod(
            self.iface.mainWindow(), "projectReadDecorationItems")
        self.iface.mapCanvas().refresh()

    def _write_copyright_entries(self):
        copyrights_text = self._parse_copyrights()
        # when no active MapTiler layer
        if copyrights_text == '':
            copyrights_text = self._default_copyright
            QgsProject.instance().writeEntry("CopyrightLabel", "/Label", copyrights_text)
            QgsProject.instance().writeEntry("CopyrightLabel", "/Enabled", False)

        else:
            QgsProject.instance().writeEntry("CopyrightLabel", "/Label", copyrights_text)
            QgsProject.instance().writeEntry("CopyrightLabel", "/Enabled", True)
        QgsProject.instance().writeEntry("CopyrightLabel", "/MarginH", 1)
        QgsProject.instance().writeEntry("CopyrightLabel", "/MarginV", 1)
        QMetaObject.invokeMethod(
            self.iface.mainWindow(), "projectReadDecorationItems")
        self.iface.mapCanvas().refresh()

    def _parse_copyrights(self):
        copyrights = []
        root_group = self.iface.layerTreeView().layerTreeModel().rootGroup()
        for l in root_group.findLayers():
            # when invalid layer is in Browser
            if not isinstance(l.layer(), QgsMapLayer):
                continue
            if l.isVisible():
                attribution = l.layer().attribution()
                attribution = re.sub(
                    '<a.*?>|</a>', '', attribution).replace('&copy;', '©').replace('©', '!!!©')
                parsed_attributions = attribution.split('!!!')
                for attr in parsed_attributions:
                    if attr == '':
                        continue

                    if not attr in copyrights:
                        copyrights.append(attr)

        return ' '.join(copyrights)

    # --------------------------------------------------------------------------

    # LineEdit edited event
    def on_searchword_edited(self):
        model = self.completer.model()
        model.setStringList([])
        self.completer.complete()

    # LineEdit returned event
    def on_searchword_returned(self):
        searchword = self.search_line_edit.text()
        geojson_dict = self._fetch_geocoding_api(searchword)

        # always dict is Non when apikey invalid
        if geojson_dict is None:
            return

        self.result_features = geojson_dict['features']

        result_list = []
        for feature in self.result_features:
            result_list.append('%s:%s' %
                               (feature['text'], feature['place_name']))

        model = self.completer.model()
        model.setStringList(result_list)
        self.completer.complete()

    def _fetch_geocoding_api(self, searchword):
        # get a center point of MapCanvas
        center = self.iface.mapCanvas().center()
        center_as_qgspoint = QgsPoint(center.x(), center.y())

        # transform the center point to EPSG:4326
        target_crs = QgsCoordinateReferenceSystem('EPSG:4326')
        transform = QgsCoordinateTransform(
            self.proj.crs(), target_crs, self.proj)
        center_as_qgspoint.transform(transform)
        center_lonlat = [center_as_qgspoint.x(), center_as_qgspoint.y()]

        # start Geocoding
        geocoder = MapTilerGeocoder()
        geojson_dict = geocoder.geocoding(searchword, center_lonlat)
        return geojson_dict

    def on_result_clicked(self, result_index):
        # add selected feature to Project
        selected_feature = self.result_features[result_index.row()]
        geojson_str = json.dumps(selected_feature)
        vlayer = QgsVectorLayer(
            geojson_str, selected_feature['place_name'], 'ogr')
        self.proj.addMapLayer(vlayer)

        # get leftbottom and righttop points of vlayer
        vlayer_extent_rect = vlayer.extent()
        vlayer_extent_leftbottom = QgsPoint(
            vlayer_extent_rect.xMinimum(), vlayer_extent_rect.yMinimum())
        vlayer_extent_righttop = QgsPoint(
            vlayer_extent_rect.xMaximum(), vlayer_extent_rect.yMaximum())

        # transform 2points to project CRS
        current_crs = vlayer.sourceCrs()
        target_crs = self.proj.crs()
        transform = QgsCoordinateTransform(current_crs, target_crs, self.proj)
        vlayer_extent_leftbottom.transform(transform)
        vlayer_extent_righttop.transform(transform)

        # make rectangle same to new extent by transformed 2points
        target_extent_rect = QgsRectangle(vlayer_extent_leftbottom.x(), vlayer_extent_leftbottom.y(),
                                          vlayer_extent_righttop.x(), vlayer_extent_righttop.y())

        self.iface.mapCanvas().zoomToFeatureExtent(target_extent_rect)
