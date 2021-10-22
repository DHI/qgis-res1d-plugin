# -*- coding: utf-8 -*-
"""
/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
import numpy as np

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.core import *
from datetime import datetime

try:
    from mikeio1d.res1d import Res1D
    from mikeio1d.dotnet import to_numpy

except ImportError:
    import sys
    import os

    this_dir = os.path.dirname(os.path.realpath(__file__))
    path = os.path.join(this_dir, os.pardir, 'mikeio1d-0.1.0-py3-none-any.whl')
    sys.path.append(path)
    path = os.path.join(this_dir, os.pardir, 'numpy-1.21.2-cp38-cp38-win_amd64.whl')
    sys.path.append(path)
    path = os.path.join(this_dir, os.pardir, 'pandas-1.3.3-cp38-cp38-win_amd64.whl')
    sys.path.append(path)
    path = os.path.join(this_dir, os.pardir, 'pycparser-2.20-py2.py3-none-any.whl')
    sys.path.append(path)
    path = os.path.join(this_dir, os.pardir, 'python_dateutil-2.8.2-py2.py3-none-any.whl')
    sys.path.append(path)
    path = os.path.join(this_dir, os.pardir, 'pythonnet-2.5.2-cp38-cp38-win_amd64.whl')
    sys.path.append(path)
    path = os.path.join(this_dir, os.pardir, 'pytz-2021.3-py2.py3-none-any.whl')
    sys.path.append(path)
    path = os.path.join(this_dir, os.pardir, 'six-1.16.0-py2.py3-none-any.whl')
    sys.path.append(path)
    from mikeio1d.res1d import Res1D


Res1DLoaderDialogUi, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'res1d_loader_dialog_base.ui'))
Res1DProgressDialogUi, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'res1d_progress_dialog_base.ui'))

class Res1dLoader(QObject):

    finished = pyqtSignal()
    taskChanged = pyqtSignal(str)
    progressChanged= pyqtSignal(int, int)

    def __init__(self):
        super(Res1dLoader, self).__init__()

        self.x_nodes = []
        self.y_nodes = []
        self.edges_start = []
        self.edges_end = []
        self.dataset_groups = {}

        self.success = False
        self.stop = False
        self.keep_edge_dataset_group_in_vertex = False
        self.keep_time_step = 1
        self.start_date_time = datetime.now()
        self.end_date_time = datetime.now()

    def load(self):

        self.success = True

        self.taskChanged.emit('Read file: '+ self.file_name)
        self.progressChanged.emit(0, 100)
        self.res1D = Res1D(self.file_name)
        self.progressChanged.emit(100, 100)

        self.taskChanged.emit('Load mesh vertices')
        self.x_nodes = [node.XCoordinate for node in self.res1D.data.Nodes]
        self.y_nodes = [node.YCoordinate for node in self.res1D.data.Nodes]

        uri_str = ''
        # build the mesh
        node_count = len(self.x_nodes)
        self.progressChanged.emit(0, node_count)
        for i in range(0, node_count):
            uri_str = uri_str + str(self.x_nodes[i]) + ', ' + str(self.y_nodes[i]) + ' \n'
            self.update_progress(i, node_count, 100)

        uri_str = uri_str + '---'

        self.taskChanged.emit('Load mesh edges')
        self.edges_start = [reach.StartNodeIndex for reach in self.res1D.data.Reaches]
        self.edges_end = [reach.EndNodeIndex for reach in self.res1D.data.Reaches]

        edge_count = len(self.edges_start)
        self.progressChanged.emit(0, edge_count)
        for i in range(0, edge_count):
            uri_str = uri_str + str(self.edges_start[i]) + ', ' + str(self.edges_end[i]) + ' \n'
            self.update_progress(i, edge_count, 100)

        self.layer = QgsMeshLayer(uri_str, "mesh1D", 'mesh_memory')

        delete_value = self.res1D.data.DeleteValue

        start_time = self.res1D.start_time
        time_steps = []
        time_index = 0

        time_index_list = []

        for time in self.res1D.data.TimesList:
            if time_index % self.keep_time_step == 0:
                dt = datetime(time.Year, time.Month, time.Day, time.Hour, time.Minute, time.Second)
                if self.start_date_time <= dt <= self.end_date_time:
                    time_index_list.append(time_index)
                    diff = (dt - start_time)
                    time_in_hours = diff.days * 24 + diff.seconds / 3600 + diff.microseconds / 3600000000
                    time_steps.append(time_in_hours)

            time_index = time_index + 1

        dataset_groups = {}

        if not self.stop:
            for quantity in self.res1D.data.Quantities:
                dataset_groups[quantity.Id] = quantity.Description

        vertex_dataset_groups=[]

        # add vertex dataset groups
        for quantity_id, quantity_description in dataset_groups.items():
            has_data = False
            data = np.full([len(time_index_list), node_count], delete_value)
            node_index = 0
            for node in self.res1D.data.Nodes:
                node_data = self.res1D.query.GetNodeValues(node.Id, quantity_id)
                if node_data is not None:
                    has_data |= True
                    np_node_data = to_numpy(node_data)
                    data[:, node_index] = np_node_data[time_index_list]
                node_index = node_index + 1

            if has_data:
                vertex_dataset_groups.append(quantity_id)
                self.taskChanged.emit('Load dataset group on vertex:' + quantity_description)
                uri_string = 'vertex scalar ' + quantity_id + '\n'
                uri_string = uri_string + '---'
                uri_string = uri_string + 'description: ' + quantity_description + '\n'
                uri_string = uri_string + 'reference_time: ' + str(start_time.date()) + \
                             'T' + str(start_time.time()) + '\n'

                time_step_count = len(time_steps)
                for t in range(0, time_step_count):
                    uri_string = uri_string + '---'
                    uri_string = uri_string + str(time_steps[t]) + ' \n'

                    self.update_progress(t, time_step_count, 100)

                    for n in range(0, node_count):
                        value_str = ''

                        if data[t, n] == delete_value:
                            value_str = '*'
                        else:
                            value_str = str(data[t, n])

                        uri_string = uri_string + value_str + ' \n'

                    if self.stop:
                        break

                if not self.stop:
                    self.success = self.success and self.layer.addDatasets(uri_string)

            if self.stop:
                break

        # add face dataset groups
        for quantity_id, quantity_description in dataset_groups.items():
            has_data = False

            if not self.keep_edge_dataset_group_in_vertex and quantity_id in vertex_dataset_groups:
                continue

            data = np.full([len(time_index_list), edge_count], delete_value)
            reach_index = 0
            for reach in self.res1D.data.Reaches:
                for di in reach.DataItems:
                    chainages = reach.GetChainages(di)
                    chainages_value = []
                    if di.Quantity.Id == quantity_id:
                        for ch in chainages:
                            chainages_value.append(ch)

                        middle_position = (chainages_value[0] + chainages_value[-1]) / 2
                        reach_data = self.res1D.query.GetReachValues(reach.Name, middle_position, quantity_id)

                        if reach_data is not None:
                            has_data |= True
                            np_reach_data = to_numpy(reach_data)
                            data[:, reach_index] = np_reach_data[time_index_list]

                reach_index = reach_index + 1

            if has_data:
                uri_string = 'edge scalar ' + quantity_id + '\n'
                uri_string = uri_string + '---'
                uri_string = uri_string + 'description: ' + quantity_description + '\n'
                uri_string = uri_string + 'reference_time: ' + str(start_time.date()) + \
                             'T' + str(start_time.time()) + ' \n'

                time_step_count = len(time_steps)
                for t in range(0, len(time_steps)):
                    uri_string = uri_string + '---'
                    uri_string = uri_string + str(time_steps[t]) + ' \n'

                    self.update_progress(t, time_step_count, 100)

                    for edge_index in range(0, edge_count):
                        value_str = ''

                        if data[t, edge_index] == delete_value:
                            value_str = '*'
                        else:
                            value_str = str(data[t, edge_index])

                        uri_string = uri_string + value_str + ' \n'
                    if self.stop:
                        break
                if not self.stop:
                    self.success = self.success and self.layer.addDatasets(uri_string)

            if self.stop:
                break

        self.finished.emit()

    def get_layer(self):
        if self.success:
            return self.layer
        else:
            return None

    def stop_loading(self):
        self.stop = True
        self.success = False

    def update_progress(self, step, maxStep, reduce_step_factor):
        if step % (max(1, int(maxStep / reduce_step_factor))) == 0:
            self.progressChanged.emit(step, maxStep)

class ProgressDialog(QDialog,Res1DProgressDialogUi):

    def __init__(self, parent=None):
        """Constructor."""
        super(ProgressDialog, self).__init__(parent)
        self.setupUi(self)
        self.setWindowTitle("loading res1d file")
        self.progress_bar.setMinimum(0)

    def set_task(self, task_name):
        self.task_name_label.setText(task_name)

    def set_progress(self, progress, max_progress):
        self.progress_bar.setMaximum(max_progress)
        self.progress_bar.setValue(progress)

class Res1DDialog(QDialog, Res1DLoaderDialogUi):
    def __init__(self, parent=None):
        """Constructor."""
        super(Res1DDialog, self).__init__(parent)
        self.setupUi(self)
        self.file_widget.fileChanged.connect(self.parseFile)
        self.button_box.accepted.connect(self.launch_loader)
        self.button_box.rejected.connect(self.reject)
        self.time_steps = []

        self.start_dateTime_edit.dateTimeChanged.connect(self.update_time_steps_count)
        self.end_dateTime_edit.dateTimeChanged.connect(self.update_time_steps_count)
        self.spin_box_keep_time_step.valueChanged.connect(self.update_time_steps_count)

    def parseFile(self, file_name):


        if os.path.isfile(file_name):

            QApplication.setOverrideCursor(Qt.WaitCursor)

            res1d = Res1D(file_name)

            x_nodes = [node.XCoordinate for node in res1d.data.Nodes]
            y_nodes = [node.YCoordinate for node in res1d.data.Nodes]
            self.nodes_count_label.setText(str(len(x_nodes)))

            edges_start = [reach.StartNodeIndex for reach in res1d.data.Reaches]
            edges_end = [reach.EndNodeIndex for reach in res1d.data.Reaches]

            self.edges_count_label.setText(str(len(edges_start)))

            self.start_dateTime_edit.setDateTime(res1d.start_time)
            self.end_dateTime_edit.setDateTime(res1d.end_time)

            self.button_box.button(QtWidgets.QDialogButtonBox.Ok).\
                setEnabled(len(x_nodes) == len(y_nodes) or len(edges_start) == len(edges_end))

            self.time_steps = []
            for time in res1d.data.TimesList:
                dt = datetime(time.Year, time.Month, time.Day, time.Hour, time.Minute, time.Second)
                self.time_steps.append(dt)

            self.update_time_steps_count()

            QApplication.restoreOverrideCursor()
        else:
            self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)

    def update_time_steps_count(self):
        start_time = self.start_dateTime_edit.dateTime()
        end_time = self.end_dateTime_edit.dateTime()
        keep_time_step = self.spin_box_keep_time_step.value()
        time_index = 0
        time_step_count = 0
        for time in self.time_steps:
            if time_index % keep_time_step == 0:
                if start_time <= time <= end_time:
                    time_step_count = time_step_count + 1

            time_index = time_index + 1

        self.time_steps_count_label.setText(str(time_step_count))

    def launch_loader(self):

        if not os.path.isfile(self.file_widget.filePath()):
            QMessageBox.warning(self, 'Load res1d file', 'File does not exist')
            return

        self.loader = Res1dLoader()
        self.loader.file_name = self.file_widget.filePath()
        self.loader.keep_edge_dataset_group_in_vertex = self.check_box_dataset_on_edge.isChecked()
        self.loader.keep_time_step=self.spin_box_keep_time_step.value()
        self.loader.start_date_time = self.start_dateTime_edit.dateTime()
        self.loader.end_date_time = self.end_dateTime_edit.dateTime()

        self.progress_dialog=ProgressDialog(self)
        self.progress_dialog.setModal(True)
        self.progress_dialog.rejected.connect(self.stop_loading)

        self.loading_thread = QThread()
        self.loader.moveToThread(self.loading_thread)
        self.loading_thread.started.connect(self.loader.load)
        self.loader.finished.connect(self.onMeshLoaded)
        self.loader.finished.connect(self.loading_thread.quit)
        self.loader.progressChanged.connect(self.progress_dialog.set_progress)
        self.loader.taskChanged.connect(self.progress_dialog.set_task)
        self.loading_thread.start()

        self.progress_dialog.show()

    def onMeshLoaded(self):
        self.progress_dialog.hide()
        layer = self.loader.get_layer()
        if layer is not None:
            layer.setCrs(self.crs_widget.crs())
            if layer.datasetGroupCount() > 0:
                settings=layer.rendererSettings()
                settings.setActiveScalarDatasetGroup(0)
                layer.setRendererSettings(settings)

            QgsProject.instance().addMapLayer(layer)
            self.file_widget.setFilePath('')
            self.accept()

    def stop_loading(self):
        self.loader.stop_loading()
