import os
import sip

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import *

from .configue_dialog import ConfigueDialog
from .new_connection_dialog import VectorNewConnectionDialog
from .edit_connection_dialog import VectorEditConnectionDialog
from .settings_manager import SettingsManager
from . import utils

import json
import requests
from .mapbox2qgis import *

IMGS_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "imgs")


def maps_icon_path():
    icon_path = os.path.join(IMGS_PATH, "icon_maps_light.svg")
    if utils.is_in_darkmode():
        icon_path = os.path.join(IMGS_PATH, "icon_maps_dark.svg")
    return icon_path


class VectorCollection(QgsDataCollectionItem):

    STANDARD_DATASET = {
        'Basic': r'https://api.maptiler.com/tiles/v3/{z}/{x}/{y}.pbf?key=',
    }

    LOCAL_JP_DATASET = {
    }

    LOCAL_NL_DATASET = {
    }

    LOCAL_UK_DATASET = {
    }

    def __init__(self, name):
        QgsDataCollectionItem.__init__(
            self, None, name, "/MapTiler/vector/" + name)

        self.setIcon(QIcon(maps_icon_path()))

        self.ALL_DATASET = dict(**self.STANDARD_DATASET,
                                **self.LOCAL_JP_DATASET,
                                **self.LOCAL_NL_DATASET,
                                **self.LOCAL_UK_DATASET)

        self.LOCAL_DATASET = dict(**self.LOCAL_JP_DATASET,
                                  **self.LOCAL_NL_DATASET,
                                  **self.LOCAL_UK_DATASET)

    def createChildren(self):
        items = []

        for key in self.ALL_DATASET:
            # skip adding if it is not recently used
            smanager = SettingsManager()
            recentmaps = smanager.get_setting('recentmaps')
            if not key in recentmaps:
                continue

            # add space to put items above
            item = VectorMapItem(self, ' ' + key, self.ALL_DATASET[key])
            sip.transferto(item, self)
            items.append(item)

        more_collection = VectorMoreCollection(
            self.STANDARD_DATASET, self.LOCAL_DATASET)
        sip.transferto(more_collection, self)
        items.append(more_collection)

        return items


class VectorMoreCollection(QgsDataCollectionItem):
    def __init__(self, dataset, local_dataset):
        QgsDataCollectionItem.__init__(
            self, None, "more...", "/MapTiler/vector/more")

        self.setIcon(QIcon(maps_icon_path()))

        self._dataset = dataset
        self._local_dataset = local_dataset

    def createChildren(self):
        items = []
        for key in self._dataset:
            # add item only when it is not recently used
            smanager = SettingsManager()
            recentmaps = smanager.get_setting('recentmaps')
            if key in recentmaps:
                continue

            # add space to put items above
            item = VectorMapItem(self, ' ' + key, self._dataset[key])
            sip.transferto(item, self)
            items.append(item)

        for key in self._local_dataset:
            # add item only when it is not recently used
            smanager = SettingsManager()
            recentmaps = smanager.get_setting('recentmaps')
            if key in recentmaps:
                continue

            # add space to put items above
            item = VectorMapItem(self, key, self._local_dataset[key])
            sip.transferto(item, self)
            items.append(item)

        return items


class VectorUserCollection(QgsDataCollectionItem):
    def __init__(self, name="User Maps"):
        QgsDataCollectionItem.__init__(
            self, None, name, "/MapTiler/vector/user")

        self.setIcon(QIcon(maps_icon_path()))

    def createChildren(self):
        items = []

        smanager = SettingsManager()
        vectormaps = smanager.get_setting('vectormaps')
        for key in vectormaps:
            item = VectorMapItem(self, key, vectormaps[key], editable=True)
            sip.transferto(item, self)
            items.append(item)

        return items

    def actions(self, parent):
        actions = []
        new = QAction(QIcon(), 'Add new connection', parent)
        new.triggered.connect(self.openDialog)
        actions.append(new)

        return actions

    def openDialog(self):
        new_dialog = VectorNewConnectionDialog()
        new_dialog.exec_()
        # reload browser
        self.refreshConnections()


class VectorMapItem(QgsDataItem):
    def __init__(self, parent, name, url, editable=False):
        QgsDataItem.__init__(self, QgsDataItem.Custom, parent,
                             name, "/MapTiler/vector/" + parent.name() + '/' + name)
        self.populate()  # set to treat Item as not-folder-like

        self._parent = parent
        self._name = name
        self._url = url
        self._editable = editable

    def acceptDrop(self):
        return False

    def handleDoubleClick(self):
        self._add_to_canvas()
        return True

    def actions(self, parent):
        actions = []

        add_action = QAction(QIcon(), 'Add to Canvas', parent)
        add_action.triggered.connect(self._add_to_canvas)
        actions.append(add_action)

        if self._editable:
            edit_action = QAction(QIcon(), 'Edit', parent)
            edit_action.triggered.connect(self._edit)
            actions.append(edit_action)

            remove_action = QAction(QIcon(), 'Remove', parent)
            remove_action.triggered.connect(self._remove)
            actions.append(remove_action)

        return actions

    def _add_to_canvas(self):
        # apikey validation
        smanager = SettingsManager()
        apikey = smanager.get_setting('apikey')
        if not utils.validate_key(apikey):
            self._openConfigueDialog()
            return True

        style_json_url = self._url + apikey
        url_zxy = self.parse_style_json(style_json_url, apikey)

        proj = QgsProject().instance()
        url = "type=xyz&url=" + url_zxy + apikey
        vector = QgsVectorTileLayer(url, self._name)

        style_json_str = requests.get(style_json_url).text
        renderer, labeling = parse_json(style_json_str)
        vector.setRenderer(renderer)
        vector.setLabeling(labeling)
        proj.addMapLayer(vector)

        if not self._editable:
            self._update_recentmaps()

    def _edit(self):
        edit_dialog = VectorEditConnectionDialog(self._name)
        edit_dialog.exec_()
        # to reload item's info, once delete item
        self._parent.deleteChildItem(self)
        self._parent.refreshConnections()

    def _remove(self):
        smanager = SettingsManager()
        vectormaps = smanager.get_setting('vectormaps')
        del vectormaps[self._name]
        smanager.store_setting('vectormaps', vectormaps)
        self._parent.refreshConnections()

    def _openConfigueDialog(self):
        configue_dialog = ConfigueDialog()
        configue_dialog.exec_()
        self._parent.parent().refreshConnections()
        self._parent.refreshConnections()

    def _update_recentmaps(self):
        smanager = SettingsManager()
        recentmaps = smanager.get_setting('recentmaps')

        # clean item name spacer
        key = self._name
        if key[0] == ' ':
            key = key[1:]

        if not key in recentmaps:
            recentmaps.append(key)

        MAX_RECENT_MAPS = 3
        if len(recentmaps) > MAX_RECENT_MAPS:
            recentmaps.pop(0)

        smanager.store_setting('recentmaps', recentmaps)
        self._parent.parent().refreshConnections()
        self._parent.refreshConnections()

    def parse_style_json(self, style_json_url, apikey):
        # https://api.maptiler.com/maps/basic/style.json?key=m6dxIgKVTnvERWrCmvUm
        if style_json_url.split("?")[0].endswith(".json"):
            style_json_data = json.loads(requests.get(style_json_url).text)
            layer_sources = style_json_data.get("sources")
            for layer_name, layer_data in layer_sources.items():
                grouped_name = f"{self._name}_{layer_name}"
                tile_json_url = layer_data.get("url")
                tile_json_data = json.loads(requests.get(tile_json_url).text)
                layer_zxy_url = tile_json_data.get("tiles")[0]

                if apikey:
                    if layer_zxy_url.endswith(apikey):
                        apikey_char_count = len(apikey) * -1
                        layer_zxy_url = layer_zxy_url[:apikey_char_count]
                return layer_zxy_url
        else:
            return self._url
