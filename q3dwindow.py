# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Q3DWindow

                              -------------------
        begin                : 2016-02-10
        copyright            : (C) 2016 Minoru Akagi
        email                : akaginch@gmail.com
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
from PyQt5.Qt import QMainWindow, QEvent, Qt
from PyQt5.QtCore import QDir, QObject, QSettings, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QIcon
from PyQt5.QtWidgets import QActionGroup, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QMessageBox, QProgressBar

from . import q3dconst
from .conf import debug_mode, plugin_version
from .exporttowebdialog import ExportToWebDialog
from .pluginmanager import pluginManager
from .propertypages import ScenePropertyPage, DEMPropertyPage, VectorPropertyPage
from .qgis2threejstools import logMessage, pluginDir
from .ui.propertiesdialog import Ui_PropertiesDialog
from .ui.q3dwindow import Ui_Q3DWindow


class Q3DViewerInterface:

  def __init__(self, qgisIface, wnd, treeView, webView, controller):
    self.qgisIface = qgisIface
    self.wnd = wnd
    self.treeView = treeView
    self.webView = webView

    self.connectToController(controller)

  def connectToController(self, controller):
    self.controller = controller
    controller.connectToIface(self)

  def disconnectFromController(self):
    if self.controller:
      self.controller.disconnectFromIface()
    self.controller = None

  def fetchLayerList(self):
    settings = self.controller.settings
    settings.updateLayerList()
    self.treeView.setLayerList(settings.getLayerList())

  def startApplication(self):
    # configuration
    p = self.controller.settings.northArrow()
    if p.get("visible"):
      self.runString("Q3D.Config.northArrow.visible = true;")
      self.runString("Q3D.Config.northArrow.color = {};".format(p.get("color", 0)))

    label = self.controller.settings.footerLabel()
    if label:
      self.runString('setFooterLabel("{}");'.format(label.replace('"', '\\"')))

    # initialize and start app
    self.runString("init();")
    self.runString("app.start();")

    if debug_mode:
      self.runString("displayFPS();")

  def setPreviewEnabled(self, enabled):
    self.controller.setPreviewEnabled(enabled)

    elem = "document.getElementById('cover')"
    self.runString("{}.style.display = '{}';".format(elem, "none" if enabled else "block"))
    if not enabled:
      self.runString("{}.innerHTML = '<img src=\"../Qgis2threejs.png\">';".format(elem))

  def loadJSONObject(self, obj):
    # display the content of the object in the debug element
    if debug_mode == 2:
      self.runString("document.getElementById('debug').innerHTML = '{}';".format(str(obj)[:500].replace("'", "\\'")))

    self.webView.sendData(obj)

  def runString(self, string, message=""):
    self.webView.runString(string, message, sourceID="q3dwindow.py")

  def abort(self):
    self.controller.abort()

  def updateScene(self, base64=False):
    if base64:
      self.controller.settings.base64 = True

    self.controller.updateScene()
    self.controller.settings.base64 = False

  def updateLayer(self, layer):
    self.controller.updateLayer(layer)

  def showMessage(self, msg):
    self.wnd.ui.statusbar.showMessage(msg)

  def clearMessage(self):
    self.wnd.ui.statusbar.clearMessage()

  def progress(self, percentage=100, text=None):
    bar = self.wnd.ui.progressBar
    if percentage == 100:
      bar.setVisible(False)
      bar.setFormat("")
    else:
      bar.setVisible(True)
      bar.setValue(percentage)
      if text is not None:
        bar.setFormat(text)

  def showScenePropertiesDialog(self):
    dialog = PropertiesDialog(self.wnd, self.qgisIface, self.controller.settings)
    dialog.propertiesAccepted.connect(self.updateSceneProperties)
    dialog.showSceneProperties()

  def updateSceneProperties(self, _, properties):
    if self.controller.settings.sceneProperties() == properties:
      return
    self.controller.settings.setSceneProperties(properties)
    self.controller.updateScene()

  def showLayerPropertiesDialog(self, layer):
    dialog = PropertiesDialog(self.wnd, self.qgisIface, self.controller.settings)
    dialog.propertiesAccepted.connect(self.updateLayerProperties)
    dialog.showLayerProperties(layer)
    return True

  def updateLayerProperties(self, layerId, properties):
    # save layer properties
    layer = self.controller.settings.getItemByLayerId(layerId)
    layer.properties = properties
    layer.updated = True

    if layer.visible:
      self.updateLayer(layer)

  def getDefaultProperties(self, layer):
    dialog = PropertiesDialog(self.wnd, self.qgisIface, self.controller.settings)
    dialog.setLayer(layer)
    return dialog.page.properties()

  def clearExportSettings(self):
    self.controller.settings.clear()
    self.controller.settings.updateLayerList()
    self.controller.updateScene()


class Q3DWindow(QMainWindow):

  def __init__(self, parent, qgisIface, controller, isViewer=True, preview=True):
    QMainWindow.__init__(self, parent)
    self.qgisIface = qgisIface
    self.isViewer = isViewer
    self.settings = controller.settings

    #if live_in_another_process:
    #  self.iface = SocketClient(serverName, self)
    #  self.iface.notified.connect(self.notified)
    #  self.iface.requestReceived.connect(self.requestReceived)
    #  self.iface.responseReceived.connect(self.responseReceived)
    #else:
    #  self.iface = Q3DConnector(self)

    self.setWindowIcon(QIcon(pluginDir("Qgis2threejs.png")))

    self.ui = Ui_Q3DWindow()
    self.ui.setupUi(self)

    self.iface = Q3DViewerInterface(qgisIface, self, self.ui.treeView, self.ui.webView, controller)

    self.setupMenu()
    self.setupContextMenu()
    self.setupStatusBar(self.iface, preview)
    self.ui.treeView.setup(self.iface)
    self.ui.webView.setup(self, self.iface, isViewer, preview)
    self.ui.dockWidgetConsole.hide()

    self.iface.fetchLayerList()

    # signal-slot connections
    # console
    self.ui.lineEditInputBox.returnPressed.connect(self.runInputBoxString)

    # to disconnect from map canvas when window is closed
    self.setAttribute(Qt.WA_DeleteOnClose)

    self.alwaysOnTopToggled(False)

    # restore window geometry and dockwidget layout
    settings = QSettings()
    self.restoreGeometry(settings.value("/Qgis2threejs/wnd/geometry", b""))
    self.restoreState(settings.value("/Qgis2threejs/wnd/state", b""))

  def closeEvent(self, event):
    self.iface.disconnectFromController()

    # save export settings to a settings file
    self.settings.saveSettings()

    settings = QSettings()
    settings.setValue("/Qgis2threejs/wnd/geometry", self.saveGeometry())
    settings.setValue("/Qgis2threejs/wnd/state", self.saveState())

    # close dialogs
    for dlg in self.findChildren((PropertiesDialog, ExportToWebDialog, NorthArrowDialog, FooterLabelDialog)):
      dlg.close()

    QMainWindow.closeEvent(self, event)

  def keyPressEvent(self, event):
    if event.key() == Qt.Key_Escape:
      self.iface.abort()
    QMainWindow.keyPressEvent(self, event)

  def setupMenu(self):
    self.ui.menuPanels.addAction(self.ui.dockWidgetLayers.toggleViewAction())
    self.ui.menuPanels.addAction(self.ui.dockWidgetConsole.toggleViewAction())

    self.ui.actionGroupCamera = QActionGroup(self)
    self.ui.actionPerspective.setActionGroup(self.ui.actionGroupCamera)
    self.ui.actionOrthographic.setActionGroup(self.ui.actionGroupCamera)
    self.ui.actionOrthographic.setChecked(self.settings.isOrthoCamera())

    # signal-slot connections
    self.ui.actionExportToWeb.triggered.connect(self.exportToWeb)
    self.ui.actionSaveAsImage.triggered.connect(self.saveAsImage)
    self.ui.actionSaveAsGLTF.triggered.connect(self.saveAsGLTF)
    self.ui.actionPluginSettings.triggered.connect(self.pluginSettings)
    self.ui.actionSceneSettings.triggered.connect(self.iface.showScenePropertiesDialog)
    self.ui.actionGroupCamera.triggered.connect(self.switchCamera)
    self.ui.actionNorthArrow.triggered.connect(self.showNorthArrowDialog)
    self.ui.actionFooterLabel.triggered.connect(self.showFooterLabelDialog)
    self.ui.actionClearAllSettings.triggered.connect(self.clearExportSettings)
    self.ui.actionResetCameraPosition.triggered.connect(self.ui.webView.resetCameraPosition)
    self.ui.actionReload.triggered.connect(self.ui.webView.reloadPage)
    self.ui.actionAlwaysOnTop.toggled.connect(self.alwaysOnTopToggled)
    self.ui.actionHelp.triggered.connect(self.help)
    self.ui.actionHomePage.triggered.connect(self.homePage)
    self.ui.actionSendFeedback.triggered.connect(self.sendFeedback)
    self.ui.actionAbout.triggered.connect(self.about)

  def setupContextMenu(self):
    # console
    self.ui.actionConsoleCopy.triggered.connect(self.copyConsole)
    self.ui.actionConsoleClear.triggered.connect(self.clearConsole)
    self.ui.listWidgetDebugView.addAction(self.ui.actionConsoleCopy)
    self.ui.listWidgetDebugView.addAction(self.ui.actionConsoleClear)

  def setupStatusBar(self, iface, previewEnabled=True):
    w = QProgressBar(self.ui.statusbar)
    w.setObjectName("progressBar")
    w.setMaximumWidth(250)
    w.setAlignment(Qt.AlignCenter)
    w.setVisible(False)
    self.ui.statusbar.addPermanentWidget(w)
    self.ui.progressBar = w

    w = QCheckBox(self.ui.statusbar)
    w.setObjectName("checkBoxPreview")
    w.setText("Preview")     #_translate("Q3DWindow", "Preview"))
    w.setChecked(previewEnabled)
    self.ui.statusbar.addPermanentWidget(w)
    self.ui.checkBoxPreview = w
    self.ui.checkBoxPreview.toggled.connect(iface.setPreviewEnabled)

  def switchCamera(self, action):
    self.settings.setCamera(action == self.ui.actionOrthographic)
    self.runString("switchCamera({0});".format("true" if self.settings.isOrthoCamera() else "false"))

  def clearExportSettings(self):
    if QMessageBox.question(self, "Qgis2threejs", "Are you sure you want to clear export settings?") == QMessageBox.Yes:
      self.ui.treeView.uncheckAll()
      self.ui.actionPerspective.setChecked(True)

      self.iface.clearExportSettings()

      self.updateNorthArrow()
      self.updateFooterLabel()

  def alwaysOnTopToggled(self, checked):
    if checked:
      self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
    else:
      self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
    self.show()

  def changeEvent(self, event):
    if self.isViewer and event.type() == QEvent.WindowStateChange:
      if self.windowState() & Qt.WindowMinimized:
        self.runString("app.pause();")
      else:
        self.runString("app.resume();")

  def copyConsole(self):
    # copy selected item(s) text to clipboard
    indices = self.ui.listWidgetDebugView.selectionModel().selectedIndexes()
    text = "\n".join([str(index.data(Qt.DisplayRole)) for index in indices])
    if text:
      QApplication.clipboard().setText(text)

  def clearConsole(self):
    self.ui.listWidgetDebugView.clear()

  def printConsoleMessage(self, message, lineNumber="", sourceID=""):
    if sourceID:
      source = sourceID if lineNumber == "" else "{} ({})".format(sourceID.split("/")[-1], lineNumber)
      text = "{}: {}".format(source, message)
    else:
      text = message
    self.ui.listWidgetDebugView.addItem(text)

  def runInputBoxString(self):
    text = self.ui.lineEditInputBox.text()
    self.ui.listWidgetDebugView.addItem("> " + text)
    result = self.ui.webView._page.mainFrame().evaluateJavaScript(text)
    if result is not None:
      self.ui.listWidgetDebugView.addItem("<- {}".format(result))
    self.ui.listWidgetDebugView.scrollToBottom()
    self.ui.lineEditInputBox.clear()

  def runString(self, string, message="", sourceID="Q3DWindow.py"):
    return self.ui.webView.runString(string, message, sourceID=sourceID)

  def exportToWeb(self):
    dialog = ExportToWebDialog(self, self.qgisIface, self.settings)
    dialog.show()
    dialog.exec_()

  def saveAsImage(self):
    if not self.ui.checkBoxPreview.isChecked():
      QMessageBox.warning(self, "Save Scene as Image", "You need to enable the preview to use this function.")
      return

    self.runString("app.showPrintDialog();")

  def saveAsGLTF(self):
    if not self.ui.checkBoxPreview.isChecked():
      QMessageBox.warning(self, "Save Scene as glTF", "You need to enable the preview to use this function.")
      return

    filename, _ = QFileDialog.getSaveFileName(self, self.tr("Save Scene As"), QDir.homePath(), "glTF files (*.gltf);;Binary glTF files (*.glb)")
    if filename:
      self.iface.updateScene(base64=True)
      self.ui.webView.runJavaScriptFile(pluginDir("js/threejs/exporters/GLTFExporter.js"))
      self.runString("saveModelAsGLTF('{0}');".format(filename))

  def pluginSettings(self):
    from .pluginsettings import SettingsDialog
    dialog = SettingsDialog(self)
    if dialog.exec_():
      pluginManager().reloadPlugins()

  def showNorthArrowDialog(self):
    dialog = NorthArrowDialog(self, self.settings)
    dialog.accepted.connect(self.updateNorthArrow)
    dialog.show()
    dialog.exec_()

  def updateNorthArrow(self):
    p = self.settings.northArrow()
    self.runString("setNorthArrowColor({0});".format(p.get("color", 0)))
    self.runString("setNorthArrowVisible({0});".format("true" if p.get("visible") else "false"))

  def showFooterLabelDialog(self):
    dialog = FooterLabelDialog(self, self.settings)
    dialog.accepted.connect(self.updateFooterLabel)
    dialog.show()
    dialog.exec_()

  def updateFooterLabel(self):
    self.runString('setFooterLabel("{0}");'.format(self.settings.footerLabel().replace('"', '\\"')))

  def help(self):
    QDesktopServices.openUrl(QUrl("https://qgis2threejs.readthedocs.io/"))

  def homePage(self):
    QDesktopServices.openUrl(QUrl("https://github.com/minorua/Qgis2threejs"))

  def sendFeedback(self):
    QDesktopServices.openUrl(QUrl("https://github.com/minorua/Qgis2threejs/issues"))

  def about(self):
    QMessageBox.information(self, "Qgis2threejs Plugin", "Plugin version: {0}".format(plugin_version), QMessageBox.Ok)


class PropertiesDialog(QDialog):

  propertiesAccepted = pyqtSignal(str, dict)

  def __init__(self, parent, qgisIface, settings):
    QDialog.__init__(self, parent)
    self.setAttribute(Qt.WA_DeleteOnClose)

    self.iface = qgisIface
    self.settings = settings
    self.mapTo3d = settings.mapTo3d

    self.wheelFilter = WheelEventFilter()

    self.currentItem = None

    # Set up the user interface from Designer.
    self.ui = Ui_PropertiesDialog()
    self.ui.setupUi(self)
    self.ui.buttonBox.clicked.connect(self.buttonClicked)

    # restore dialog geometry
    settings = QSettings()
    self.restoreGeometry(settings.value("/Qgis2threejs/propdlg/geometry", b""))

    #self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
    #self.activateWindow()

  def closeEvent(self, event):
    # save dialog geometry
    settings = QSettings()
    settings.setValue("/Qgis2threejs/propdlg/geometry", self.saveGeometry())
    QDialog.closeEvent(self, event)

  def setLayer(self, layer):
    self.layer = layer
    if layer.geomType == q3dconst.TYPE_DEM:
      self.page = DEMPropertyPage(self, self)
      self.page.setup(layer)
    elif layer.geomType == q3dconst.TYPE_IMAGE:
      return
    else:
      self.page = VectorPropertyPage(self, self)
      self.page.setup(layer)
    self.ui.scrollArea.setWidget(self.page)

    # disable wheel event for ComboBox widgets
    for w in self.ui.scrollArea.findChildren(QComboBox):
      w.installEventFilter(self.wheelFilter)

  def buttonClicked(self, button):
    role = self.ui.buttonBox.buttonRole(button)
    if role in [QDialogButtonBox.AcceptRole, QDialogButtonBox.ApplyRole]:
      if isinstance(self.page, ScenePropertyPage):
        self.propertiesAccepted.emit("", self.page.properties())
      else:
        self.propertiesAccepted.emit(self.layer.layerId, self.page.properties())

  def showLayerProperties(self, layer):
    self.setWindowTitle("{0} - Layer Properties".format(layer.name))
    self.setLayer(layer)
    self.show()
    self.exec_()

  def showSceneProperties(self):
    self.setWindowTitle("Scene Settings")
    self.page = ScenePropertyPage(self, self)
    self.page.setup(self.settings.sceneProperties())
    self.ui.scrollArea.setWidget(self.page)
    self.show()
    self.exec_()


class WheelEventFilter(QObject):

  def eventFilter(self, obj, event):
    if event.type() == QEvent.Wheel:
      return True
    return QObject.eventFilter(self, obj, event)


class NorthArrowDialog(QDialog):

  def __init__(self, parent, settings):
    QDialog.__init__(self, parent)
    self.setAttribute(Qt.WA_DeleteOnClose)

    self.settings = settings

    from .ui.northarrowdialog import Ui_NorthArrowDialog
    self.ui = Ui_NorthArrowDialog()
    self.ui.setupUi(self)

    p = settings.northArrow()
    self.ui.groupBox.setChecked(p["visible"])
    self.ui.colorButton.setColor(QColor(p["color"].replace("0x", "#")))

    self.ui.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.accepted)
    self.accepted.connect(self.updateSettings)

  def updateSettings(self):
    self.settings.setNorthArrow(self.ui.groupBox.isChecked(), self.ui.colorButton.color().name().replace("#", "0x"))


class FooterLabelDialog(QDialog):

  def __init__(self, parent, settings):
    QDialog.__init__(self, parent)
    self.setAttribute(Qt.WA_DeleteOnClose)

    self.settings = settings

    from .ui.footerlabeldialog import Ui_FooterLabelDialog
    self.ui = Ui_FooterLabelDialog()
    self.ui.setupUi(self)

    self.ui.textEdit.setPlainText(settings.footerLabel())

    self.ui.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.accepted)
    self.accepted.connect(self.updateSettings)

  def updateSettings(self):
    self.settings.setFooterLabel(self.ui.textEdit.toPlainText())
