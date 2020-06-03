import json
import urllib
import requests


from qgis.PyQt.QtCore import Qt, QModelIndex, QSettings
from qgis.PyQt.QtWidgets import QDockWidget, QCompleter, QLineEdit
from qgis.core import *

from .configue_dialog import ConfigueDialog
from .settings_manager import SettingsManager
from . import utils


class MapTilerGeocoder:
    def __init__(self, language='en'):
        self._language = language

    def geocoding(self, searchword, center_lonlat):
        # apikey validation
        smanager = SettingsManager()
        apikey = smanager.get_setting('apikey')
        if not utils.validate_key(apikey):
            self._openConfigueDialog()
            return

        proximity = '%s,%s' % (str(center_lonlat[0]), str(center_lonlat[1]))
        params = {
            'key': apikey,
            'proximity': proximity,
            'language': self._language
        }
        p = urllib.parse.urlencode(params, safe=',')

        query = urllib.parse.quote(searchword)
        url = 'https://api.maptiler.com/geocoding/' + query + '.json?' + p
        geojson_str = requests.get(url).text
        geojson_dict = json.loads(geojson_str)
        return geojson_dict

    def _openConfigueDialog(self):
        configue_dialog = ConfigueDialog()
        configue_dialog.exec_()


class MapTilerGeocoderToolbar:
    def __init__(self, iface):
        # TODO: We are going to let the user set this up in a future iteration
        self.iface = iface
        self.proj = QgsProject.instance()
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
        locale = QSettings().value('locale/globalLocale')[0:2]
        geocoder = MapTilerGeocoder(locale)
        geojson_dict = geocoder.geocoding(searchword, center_lonlat)
        return geojson_dict

    def on_result_clicked(self, result_index):
        # add selected feature to Project
        selected_feature = self.result_features[result_index.row()]
        geojson_str = json.dumps(selected_feature)
        bbox = selected_feature.get("bbox")

        vlayer = QgsVectorLayer(
            geojson_str, selected_feature['place_name'], 'ogr')
        self.proj.addMapLayer(vlayer)

        extent_rect = QgsRectangle()
        current_crs = QgsCoordinateReferenceSystem()
        if bbox:
            extent_rect = QgsRectangle(bbox[0], bbox[1], bbox[2], bbox[3])
            # bbox is always defined with Longitude and Latitude
            current_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        else:
            extent_rect = vlayer.extent()
            current_crs = vlayer.sourceCrs()

        extent_leftbottom = QgsPoint(
            extent_rect.xMinimum(), extent_rect.yMinimum())
        extent_righttop = QgsPoint(
            extent_rect.xMaximum(), extent_rect.yMaximum())

        # transform 2points to project CRS
        target_crs = self.proj.crs()
        transform = QgsCoordinateTransform(current_crs, target_crs, self.proj)
        extent_leftbottom.transform(transform)
        extent_righttop.transform(transform)

        # make rectangle same to new extent by transformed 2points
        extent_rect = QgsRectangle(extent_leftbottom.x(), extent_leftbottom.y(),
                                   extent_righttop.x(), extent_righttop.y())

        self.iface.mapCanvas().zoomToFeatureExtent(extent_rect)
