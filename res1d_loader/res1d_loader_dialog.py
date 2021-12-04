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
import math

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.core import *
from datetime import datetime

from mikeio1d.res1d import Res1D
from mikeio1d.dotnet import to_numpy

Res1DLoaderDialogUi, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'res1d_loader_dialog_base.ui'))
Res1DProgressDialogUi, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'res1d_progress_dialog_base.ui'))


class DHIVertex:

    def __init__(self):
        self.X = 0
        self.Y = 0
        self.chainage = -1
        self.qgis_index = -1

    def distance(self, other):
        return math.sqrt((self.X-other.X)**2+(self.Y-other.Y)**2)

class DHIEdge:

    def __init__(self):
        self.first_vertex=-1
        self.second_vertex=-1
        self.chainage =-1
        self.qgis_index = -1

class DHIReach:

    def __init__(self):
        self.start_vertex = -1
        self.end_vertex = -1
        self.quantities_chainage = {}
        self.internal_vertices = []
        self.edges = []
        self.data = None

    def vertex_values(self, data, quantity, time_index_list, delete_value):

        if not self.internal_vertices:
            return

        data_item_index = self.quantities_chainage[quantity][0]
        item_chainages = self.quantities_chainage[quantity][1]
        # search lesser and greater chainage
        lesser = -1
        greater = -1
        data_item = list(self.data.DataItems)[data_item_index]
        time_data = data_item.TimeData

        reach_values = np.full([len(time_index_list), len(item_chainages)], delete_value)
        reach_values[:, 0] = data[:, self.start_vertex]
        reach_values[:, len(item_chainages) - 1] = data[:, self.end_vertex]

        for it in range(0, len(time_index_list)):
            reach_values[it, :] = to_numpy(time_data.GetValues(time_index_list[it]))

        for vertex in self.internal_vertices:

            for i in range(0, len(item_chainages) - 1):
                ch1 = item_chainages[i]
                ch2 = item_chainages[i + 1]
                if ch1 <= vertex.chainage <= ch2:
                    lesser = i
                    greater = i + 1
                    break

            if lesser < 0:
                return

            time_values1 = reach_values[:, lesser]

            if vertex.chainage == item_chainages[lesser]:
                data[:, vertex.qgis_index] = time_values1
            else:
                time_values2 = reach_values[:, greater]
                if vertex.chainage == item_chainages[greater]:
                    data[:, vertex.qgis_index] = time_values2
                else:
                    ch1 = item_chainages[lesser]
                    ch2 = item_chainages[greater]
                    interpolated = (time_values2 - time_values1) / (ch2 - ch1) * (vertex.chainage - ch1) + time_values1

                    data[:, vertex.qgis_index] = interpolated


class Res1dLoader(QObject):

    finished = pyqtSignal()
    taskChanged = pyqtSignal(str)
    progressChanged= pyqtSignal(int, int)

    def __init__(self):
        super(Res1dLoader, self).__init__()

        self.dataset_groups = {}

        self.success = False
        self.stop = False
        self.keep_time_step = 1
        self.start_date_time = datetime.now()
        self.end_date_time = datetime.now()

        self.res_1D = None
        self.main_nodes = []
        self.reaches = []
        self.vertices = []
        self.dhi_reaches = []
        self.node_quantities = []
        self.reach_quantities = []
        self.edge_count = 0

        self.vertex_on_grid = False
        self.vertex_on_digi = False
        self.dataset_on_edge_if_on_vertex = False

    def create_mesh(self):

        self.dataset_groups = {}
        self.reaches = []
        self.vertices = []
        self.dhi_reaches = []
        self.node_quantities = []
        self.reach_quantities = []
        self.main_nodes = []
        self.edge_count = 0
        self.reaches = []

        if not os.path.isfile(self.file_name):
            return

        self.res_1D = Res1D(self.file_name)

        self.main_nodes = list(self.res_1D.data.Nodes)
        for node in self.main_nodes:
            vert = DHIVertex()
            vert.X = node.XCoordinate
            vert.Y = node.YCoordinate
            vert.qgis_index = len(self.vertices)
            self.vertices.append(vert)
            data_items = list(node.DataItems)
            for data_item in data_items:
                if data_item.Quantity.Id not in self.node_quantities:
                    self.node_quantities.append(data_item.Quantity.Id)

        self.reaches = list(self.res_1D.data.Reaches)
        for reach in self.reaches:
            dhi_reach = DHIReach()
            data_items = list(reach.DataItems)
            dhi_reach.start_vertex = reach.StartNodeIndex
            dhi_reach.end_vertex = reach.EndNodeIndex
            grid_points = list(reach.GridPoints)

            start_chainage = grid_points[0].Chainage

            internal_chainage_vertices = []

            for i in range(0, len(data_items)):
                data_item = data_items[i]

                if not data_item.Quantity.Id in self.reach_quantities:
                    self.reach_quantities.append(data_item.Quantity.Id)
                chainages = reach.GetChainages(data_item)
                dhi_reach.quantities_chainage[data_item.Quantity.Id] = (i, list(chainages))

                if self.vertex_on_grid and data_item.Quantity.Id in self.node_quantities:
                    for ci in range(1, len(chainages) - 1):
                        dhi_vertex = DHIVertex()
                        if chainages[ci] not in internal_chainage_vertices:
                            grid_point_index = reach.GridPointIndexForChainage(chainages[ci])
                            grid_point = grid_points[grid_point_index]
                            dhi_vertex.X = grid_point.X
                            dhi_vertex.Y = grid_point.Y
                            dhi_vertex.chainage = chainages[ci]
                            dhi_reach.internal_vertices.append(dhi_vertex)
                            internal_chainage_vertices.append(chainages[ci])

            if self.vertex_on_digi:
                digi_points = list(reach.DigiPoints)
                chainage = start_chainage
                for i in range(1, len(digi_points) - 1):
                    point1 = digi_points[i - 1]
                    point2 = digi_points[i]
                    dist = math.sqrt((point1.X - point2.X) ** 2 + (point1.Y - point2.Y) ** 2)
                    chainage = chainage + dist
                    if chainage not in internal_chainage_vertices:
                        dhi_vertex = DHIVertex()
                        dhi_vertex.X = point2.X
                        dhi_vertex.Y = point2.Y
                        dhi_vertex.chainage = chainage
                        dhi_reach.internal_vertices.append(dhi_vertex)
                        internal_chainage_vertices.append(chainage)

            dhi_reach.internal_vertices = sorted(dhi_reach.internal_vertices, key = lambda vert: vert.chainage)

            # adding grip points and digi points can leads to have too close vertices, here we remove them
            vert_pos = 0
            while vert_pos < len(dhi_reach.internal_vertices)-1:
                dist = dhi_reach.internal_vertices[vert_pos].distance(dhi_reach.internal_vertices[vert_pos+1])
                if dist < 0.01:
                    del dhi_reach.internal_vertices[vert_pos]
                else:
                    vert_pos = vert_pos+1

            # set global index of vertices
            start_qgis_index = len(self.vertices)
            for ind in range(0, len(dhi_reach.internal_vertices)):
                dhi_reach.internal_vertices[ind].qgis_index = ind + start_qgis_index

            self.vertices.extend(dhi_reach.internal_vertices)

            # populate edges with index
            edge = DHIEdge()
            edge.first_vertex = dhi_reach.start_vertex
            edge.qgis_index = self.edge_count
            if not dhi_reach.internal_vertices:
                edge.second_vertex = dhi_reach.end_vertex
                edge.chainage = (grid_points[0].Chainage+grid_points[-1].Chainage)/2
            else:
                edge.second_vertex = dhi_reach.internal_vertices[0].qgis_index
                edge.chainage = (grid_points[0].Chainage + dhi_reach.internal_vertices[0].chainage) / 2

            dhi_reach.edges.append(edge)
            self.edge_count=self.edge_count+1

            if len(dhi_reach.internal_vertices) > 1:
                for ind in range(0, len(dhi_reach.internal_vertices)-1):
                    edge = DHIEdge()
                    edge.first_vertex = dhi_reach.internal_vertices[ind].qgis_index
                    edge.second_vertex = dhi_reach.internal_vertices[ind + 1].qgis_index
                    edge.chainage = (dhi_reach.internal_vertices[ind].chainage +
                                     dhi_reach.internal_vertices[ind + 1].chainage)/2
                    edge.qgis_index = self.edge_count
                    dhi_reach.edges.append(edge)
                    self.edge_count = self.edge_count + 1

            if dhi_reach.internal_vertices:
                edge = DHIEdge()
                edge.first_vertex = dhi_reach.internal_vertices[-1].qgis_index
                edge.second_vertex = dhi_reach.end_vertex
                edge.qgis_index = self.edge_count
                edge.chainage = (dhi_reach.internal_vertices[-1].chainage + grid_points[-1].Chainage) / 2
                dhi_reach.edges.append(edge)
                self.edge_count = self.edge_count + 1

            dhi_reach.data = reach
            self.dhi_reaches.append(dhi_reach)

    def load_dataset_group(self):

        dataset_groups = {}

        if not self.stop:
            for quantity in self.res_1D.data.Quantities:
                dataset_groups[quantity.Id] = quantity.Description

        delete_value = self.res_1D.data.DeleteValue

        start_time = self.res_1D.start_time
        time_steps = []
        time_index = 0

        time_index_list = []

        for time in self.res_1D.data.TimesList:
            if time_index % self.keep_time_step == 0:
                dt = datetime(time.Year, time.Month, time.Day, time.Hour, time.Minute, time.Second)
                if self.start_date_time <= dt <= self.end_date_time:
                    time_index_list.append(time_index)
                    diff = (dt - start_time)
                    time_in_hours = diff.days * 24 + diff.seconds / 3600 + diff.microseconds / 3600000000
                    time_steps.append(time_in_hours)

            time_index = time_index + 1

        # dataset group on vertices
        vertex_dataset_groups = []

        for quantity in self.node_quantities:

            data = np.full([len(time_index_list), len(self.vertices)], delete_value)

            self.taskChanged.emit('load ' + dataset_groups[quantity] + 'on vertices')
            for i in range(0, len(self.main_nodes)):
                self.update_progress(i, len(self.main_nodes), 100)

                node = self.main_nodes[i]
                data_items = list(node.DataItems)
                for data_item in data_items:
                    if data_item.NumberOfTimeSteps != len(time_steps):
                        continue
                    if data_item.Quantity.Id != quantity:
                        continue
                    values_for_time_step = [None]*len(time_index_list)
                    for t in range(0, len(time_steps)):
                        values = to_numpy(data_item.TimeData.GetValues(t))
                        if len(values) < 1:
                            continue
                        values_for_time_step[t] = values[0]
                    np_node_data = np.array(values_for_time_step)
                    data[:, i] = np_node_data[time_index_list]

            self.taskChanged.emit('load ' + dataset_groups[quantity] + ' on vertices in reaches')

            for reach_index in range(0, len(self.reaches)):
                dhi_reach = self.dhi_reaches[reach_index]
                
                self.update_progress(reach_index, len(self.reaches), 100)
                dhi_reach.vertex_values(data, quantity, time_index_list, delete_value)

            vertex_dataset_groups.append(quantity)
            self.taskChanged.emit('Load dataset group on vertex:' + dataset_groups[quantity])
            uri_string = 'vertex scalar ' + quantity + '\n'
            uri_string = uri_string + '---'
            uri_string = uri_string + 'description: ' + dataset_groups[quantity] + '\n'
            uri_string = uri_string + 'reference_time: ' + str(start_time.date()) + \
                                 'T' + str(start_time.time()) + '\n'

            time_step_count = len(time_steps)
            time_step_string = [None] * time_step_count
            for t in range(0, time_step_count):
                self.update_progress(t, time_step_count, 100)
                time_step_string[t] = '---'
                time_step_string[t] = time_step_string[t] + str(time_steps[t]) + ' \n'

                value_str = [None] * len(self.vertices)

                for n in range(0, len(self.vertices)):
                    if data[t, n] == 0:
                        value_str[n] = '*'
                    else:
                        value_str[n] = str(data[t, n])

                    value_str[n] = value_str[n] + ' \n'

                time_step_string[t] = time_step_string[t] + ''.join(value_str)

            uri_string = uri_string + ''.join(time_step_string)

            if not self.stop:
                self.success = self.success and self.layer.addDatasets(uri_string)

        # dataset group on edges
        for quantity in self.reach_quantities:
            has_data = False

            if quantity in self.node_quantities and not self.dataset_on_edge_if_on_vertex:
                continue

            data = np.full([len(time_index_list), self.edge_count], delete_value)

            self.taskChanged.emit('Load dataset group on edges:' + dataset_groups[quantity])

            for reach in self.dhi_reaches:
                self.taskChanged.emit('Load dataset group on edges:' + dataset_groups[quantity] + ' reach ' + reach.data.Name)
                for edge in reach.edges:
                    values = self.res_1D.query.GetReachValues(reach.data.Name, edge.chainage, quantity)
                    if values is not None:
                        has_data = has_data | True
                        data[:, edge.qgis_index] = to_numpy(values)[time_index_list]

            if has_data:
                uri_string = 'edge scalar ' + quantity + '\n'
                uri_string = uri_string + '---'
                uri_string = uri_string + 'description: ' + dataset_groups[quantity] + '\n'
                uri_string = uri_string + 'reference_time: ' + str(start_time.date()) + \
                             'T' + str(start_time.time()) + ' \n'

                time_step_count = len(time_steps)
                time_step_string = [None] * time_step_count
                for t in range(0, len(time_steps)):
                    time_step_string[t] = '---'
                    time_step_string[t] = time_step_string[t] + str(time_steps[t]) + ' \n'

                    self.update_progress(t, time_step_count, 100)
                    values_string = [None] * self.edge_count
                    for edge_index in range(0, self.edge_count):
                        if data[t, edge_index] == delete_value:
                            values_string[edge_index] = '*' + ' \n'
                        else:
                            values_string[edge_index] = str(data[t, edge_index]) + ' \n'

                    time_step_string[t] = time_step_string[t] + ''.join(values_string)
                    if self.stop:
                        break

                uri_string = uri_string + ''.join(time_step_string)

                if not self.stop:
                    self.success = self.success and self.layer.addDatasets(uri_string)

            if self.stop:
                break

    def load(self):

        self.success = True
        self.taskChanged.emit('create mesh')
        self.create_mesh()

        uri_str = ''
        # build the mesh
        self.taskChanged.emit('Load vertices in QGIS')
        self.progressChanged.emit(0, len(self.vertices))

        for i in range(0, len(self.vertices)):
            vertex = self.vertices[i]
            uri_str = uri_str + str(vertex.X) + ', ' + str(vertex.Y) + ' \n'
            self.update_progress(i, len(self.vertices), 100)

        uri_str = uri_str + '---'

        self.progressChanged.emit(0, len(self.dhi_reaches))

        self.taskChanged.emit('Load edges in QGIS')
        for i in range(0, len(self.dhi_reaches)):
            reach = self.dhi_reaches[i]
            edge_str=[None]*len(reach.edges)
            for ei in range(0, len(reach.edges)):
                edge_str[ei] = str(reach.edges[ei].first_vertex) + ', ' + str(reach.edges[ei].second_vertex) + ' \n'
            uri_str = uri_str+''.join(edge_str)

            self.update_progress(i,  len(self.dhi_reaches), 100)

        self.layer = QgsMeshLayer(uri_str, "mesh1D", 'mesh_memory')

        self.load_dataset_group()
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
        self.checkBox_on_grid_points.clicked.connect(self.pre_build_mesh)
        self.checkBox_on_digi_points.clicked.connect(self.pre_build_mesh)
        self.time_steps = []

        self.start_dateTime_edit.dateTimeChanged.connect(self.update_time_steps_count)
        self.end_dateTime_edit.dateTimeChanged.connect(self.update_time_steps_count)
        self.spin_box_keep_time_step.valueChanged.connect(self.update_time_steps_count)

        self.progress_dialog=ProgressDialog(self)
        self.progress_dialog.setModal(True)
        self.progress_dialog.rejected.connect(self.stop_loading)

        self.loader = Res1dLoader()
        self.loading_thread = QThread()
        self.loader.moveToThread(self.loading_thread)
        self.loading_thread.started.connect(self.loader.load)
        self.loader.finished.connect(self.on_mesh_loaded)
        self.loader.finished.connect(self.loading_thread.quit)
        self.loader.progressChanged.connect(self.progress_dialog.set_progress)
        self.loader.taskChanged.connect(self.progress_dialog.set_task)

        self.checkBox_on_digi_points.setChecked(True)

    def parseFile(self, file_name):

        if os.path.isfile(file_name):

            QApplication.setOverrideCursor(Qt.WaitCursor)

            res1d = Res1D(file_name)

            x_nodes = [node.XCoordinate for node in res1d.data.Nodes]
            y_nodes = [node.YCoordinate for node in res1d.data.Nodes]
            self.nodes_count_label.setText(str(len(x_nodes)))

            edges_start = [reach.StartNodeIndex for reach in res1d.data.Reaches]
            edges_end = [reach.EndNodeIndex for reach in res1d.data.Reaches]

            self.reaches_count_label.setText(str(len(edges_start)))

            self.start_dateTime_edit.setDateTime(res1d.start_time)
            self.end_dateTime_edit.setDateTime(res1d.end_time)

            self.button_box.button(QtWidgets.QDialogButtonBox.Ok).\
                setEnabled(len(x_nodes) == len(y_nodes) or len(edges_start) == len(edges_end))

            self.time_steps = []
            for time in res1d.data.TimesList:
                dt = datetime(time.Year, time.Month, time.Day, time.Hour, time.Minute, time.Second)
                self.time_steps.append(dt)

            self.update_time_steps_count()

            self.pre_build_mesh()

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

    def pre_build_mesh(self):

        self.loader.vertex_on_grid = self.checkBox_on_grid_points.isChecked()
        self.loader.vertex_on_digi = self.checkBox_on_digi_points.isChecked()

        self.loader.file_name = self.file_widget.filePath()
        self.loader.create_mesh()

        self.vertices_count_label.setText(str(len(self.loader.vertices)))
        self.edges_count_label.setText(str(self.loader.edge_count))

    def launch_loader(self):

        if not os.path.isfile(self.file_widget.filePath()):
            QMessageBox.warning(self, 'Load res1d file', 'File does not exist')
            return

        self.loader.file_name = self.file_widget.filePath()
        self.loader.dataset_on_edge_if_on_vertex = self.check_box_dataset_on_edge.isChecked()
        self.loader.keep_time_step=self.spin_box_keep_time_step.value()
        self.loader.start_date_time = self.start_dateTime_edit.dateTime()
        self.loader.end_date_time = self.end_dateTime_edit.dateTime()

        self.loading_thread.start()

        self.progress_dialog.show()

    def on_mesh_loaded(self):
        self.progress_dialog.hide()
        layer = self.loader.get_layer()
        if layer is not None:
            layer.setCrs(self.crs_widget.crs())
            if layer.datasetGroupCount() > 0:
                settings = layer.rendererSettings()
                settings.setActiveScalarDatasetGroup(0)
                layer.setRendererSettings(settings)

            QgsProject.instance().addMapLayer(layer)
            self.file_widget.setFilePath('')
            self.accept()

    def stop_loading(self):
        self.loader.stop_loading()
