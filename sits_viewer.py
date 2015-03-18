# -*- coding: utf-8 -*-
"""
/***************************************************************************
 sits_viewer
                                 A QGIS plugin
 Plugin for Satellite Image Time Series visualization

                              -------------------
        begin                : 2014-10-27
        copyright            : (C) 2014 by Victor Maus/INPE
        email                : victor.maus@inpe.br
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 3 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# Import the PyQt and QGIS libraries
import qgis
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
import os.path
import numpy as np
import matplotlib.pyplot as plt
import urllib2
import json 
import datetime
import time
import unicodedata
import scipy

# Initialize Qt resources from file resources.py
import resources_rc
# Import the code for the dialog
from sits_viewerdialog import sits_viewerDialog


class sits_viewer:



    def __init__(self, iface):
        # Save reference to the QGIS interface
        self.iface = iface
        # refernce to map canvas
        self.canvas = self.iface.mapCanvas()
        # out click tool will emit a QgsPoint on every click
        self.clickTool = QgsMapToolEmitPoint(self.canvas)
        # create our GUI dialog
        self.dlg = sits_viewerDialog()
        # creat a list to hold our selected features ids
        self.selectList = []
        # current layer ref (set in handleLayerChange)
        self.cLayer = None #self.canvas.currentLayer()
        # current layer dataProvider ref (set in handleLayerChange)
        self.provider = None
        # Makers list
        self.markers = []


    
    def initGui(self):
        # Create action that will start plugin configuration
        self.action = QAction(QIcon(":/plugins/sits_viewer/icon.png"), \
            "SITS Viewer", self.iface.mainWindow())
        # connect the action to the run method
        QObject.connect(self.action, SIGNAL("triggered()"), self.run)

        # Add toolbar button and menu item
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&some text that appears in the menu", self.action)
        
        # Init fields
        self.initFields()
               
        # connect our custom function to a clickTool signal that the canvas was clicked
        QObject.connect(self.clickTool, SIGNAL("canvasClicked(const QgsPoint &, Qt::MouseButton)"), self.getCoordinatesMouseDown)
        
        # Update dataset list
        QObject.connect(self.dlg.ui.listWidget_products, SIGNAL("itemDoubleClicked(QListWidgetItem *)"), self.update_datasetList)
        QObject.connect(self.dlg.ui.pushButton_showcoverages, SIGNAL("clicked()"), self.update_datasetList)
        
        # Update plot
        QObject.connect(self.dlg.ui.pushButton_plot, SIGNAL("clicked()"), self.plotTimeSeries)
        
        # Save CSV
        QObject.connect(self.dlg.ui.pushButton_save, SIGNAL("clicked()"), self.saveCSV)
        
        # Clear points
        QObject.connect(self.dlg.ui.pushButton_clear_points, SIGNAL("clicked()"), plt.close)
        
        # Close windows and clear fields
        QObject.connect(self.dlg.ui.buttonBox, SIGNAL("rejected()"), self.closePlugin)

   
       
    def unload(self):
        # Remove the plugin menu item and icon
        self.closePlugin()
        self.iface.removePluginMenu("&some text that appears in the menu",self.action)
        self.iface.removeToolBarIcon(self.action)
   
    # Init interface 
    def initFields(self):
        self.dlg.setTextBrowser(str("The time period is not implemented yet, but it is possible to zoom in the plot window.\nTo start using the tool select one product.\nThen select one or more datasets and either click in the map or tipe the coordinates."))
        self.dlg.clearProducts()
        self.getProducts()
        
    # Close plugin
    def closePlugin(self):
        self.clearPoints()
        self.dlg.clearTextBrowser()
        self.dlg.clearDatasets()
        self.dlg.clearTextCoordinates()
        plt.close()
        self.initFields()
    
    # Check server
    def url_exists(self, location):
        request = urllib2.Request(location)
        request.get_method = lambda : 'HEAD'
        try:
            response = urllib2.urlopen(request)
            return True
        except urllib2.HTTPError:
            return False
          
    # Clear points in the canvas 
    def clearPoints(self):
        for m in self.markers:
            self.canvas.scene().removeItem(m)
        del self.markers[:]   
   
    # Get satellite products from
    def getProducts(self):
        serverURL = str("http://www.dpi.inpe.br/mds/mds/product_list?&output_format=json")
        if not(self.url_exists(serverURL)):
            # update TextBrowser
            self.dlg.setTextBrowser(  str("The server does not respond. Connection timed out "+serverURL)  ) 
            QMessageBox.information( self.iface.mainWindow(),"Info", "The server does not respond. Connection timed out!" )
        else:
            response = urllib2.urlopen(serverURL)
            data = json.load(response)
            nProducts = len(data["products"])
            for i in range(nProducts):
                product = unicodedata.normalize('NFKD', data["products"][i]).encode('ascii','ignore')
                self.dlg.addProducts(str(product))
        
 
    # Update coverage list for selecte products
    def update_datasetList(self):
        self.dlg.clearDatasets()
        
        # Check MODIS produc selection
        products = self.dlg.ui.listWidget_products.selectedItems()
        if not(products):
            QMessageBox.information( self.iface.mainWindow(),"Info", "Missing the product. \nPlease select one MODIS product." )
            return None
        
        for i in list(products):
            # Check server connection 
            serverURL = str("http://www.dpi.inpe.br/mds/mds/dataset_list?product="+str(i.text())+"&output_format=json")
            if not(self.url_exists(serverURL)):
                self.dlg.setTextBrowser(  str("The server does not respond. Connection timed out "+serverURL)  ) 
                return None
            # Get datasets list and add to QlistWidget
            response = urllib2.urlopen(serverURL)
            data = json.load(response)
            datasetsList = data["datasets"]
            nDatasets = len(datasetsList)
            for j in range(nDatasets):
                datasetName = unicodedata.normalize('NFKD', datasetsList[j]).encode('ascii','ignore')
                if datasetName!="day2" and datasetName!="day" and datasetName!="day2" and datasetName!="quality" and datasetName!="reliability" and datasetName!="viewangle":
                  self.dlg.ui.listWidget_datasets.addItem(str(i.text())+str(".")+str(datasetName))
   
   
    # Save csv file with the time series 
    def saveCSV(self):
        QMessageBox.information( self.iface.mainWindow(),"Info", "Sorry! Not yet." )
        filepath = QFileDialog.getOpenFileName()
        self.dlg.setTextBrowser(str(filepath))
    
    # Get map canvas Crs 
    def getCrs(self):
        iface = qgis.utils.iface
        mc = iface.mapCanvas()
        mr = mc.mapRenderer()
        res = mr.destinationCrs()
        return res
    
    # Create WGS84 Crs 
    def createWGS84Crs(self):
        res = QgsCoordinateReferenceSystem()
        res.createFromProj4("+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs")
        return res
      
    # Get coordinates from clicked point and convert to WGS84
    def getCoordinatesMouseDown(self, point, button):
        canvasCrs = self.getCrs()
        LLCrs = self.createWGS84Crs()
        CoordinateTransform = qgis.core.QgsCoordinateTransform
        point = CoordinateTransform(canvasCrs, LLCrs).transform(point)
        self.dlg.clearTextCoordinates()
        self.dlg.setTextCoordinates(str(point.x())+","+str(point.y()))
        self.plotTimeSeries()

    # Draw point in the canvas
    def drawPoint(self, point):
        canvasCrs = self.getCrs()
        LLCrs = self.createWGS84Crs()
        CoordinateTransform = qgis.core.QgsCoordinateTransform
        point = CoordinateTransform(LLCrs, canvasCrs).transform(point)
        m = QgsVertexMarker(self.canvas)
        m.setCenter(point)
        m.setColor(QColor(255, 0, 0))
        m.setIconSize(10)
        m.setIconType(QgsVertexMarker.ICON_X) # or ICON_CROSS, ICON_X
        m.setPenWidth(2)
        self.markers.append(m)
        
    # Process dates 
    def transform_dates(self, timeline):
        N = len(timeline)
        for i in range(N):
           timeline[i] = unicodedata.normalize('NFKD', timeline[i]).encode('ascii','ignore')
           timeline[i] = datetime.datetime.strptime(timeline[i], "%Y-%m-%d") 
        return timeline
    
    # Process coverage
    def compute_pre_processing(self, data):
        scale_factor = float(data["scale_factor"])
        missing_value = data["missing_value"]
        values = data["values"]
        N = len(values)
        for i in range(N):
           if values[i]==missing_value:
              values[i] = float('NaN')
           else:
              values[i] = values[i] / float(scale_factor)
        return values

    # Get time series for a item
    def getTimeSeries(self, item, point):
         product = str(item.text()).split('.', 1 )[0]
         dataset = str(item.text()).split('.', 1 )[1]
        
         serverURL = str("http://www.dpi.inpe.br/mds/mds/query?product="+str(product)+"&datasets="+str(dataset)+
                          "&longitude="+str(point.x())+"&latitude="+str(point.y())+"&output_format=json")

         # Check server connection 
         if not(self.url_exists(serverURL)):
            self.dlg.setTextBrowser(  str("The server does not respond. Connection timed out for: "+serverURL)  )
            QMessageBox.information( self.iface.mainWindow(),"Info", "The server does not respond. \nConnection timed out!\n"+serverURL )
            return False
      
         # get datasets from server
         response = urllib2.urlopen(serverURL)
         data = json.load(response)
            
         # Check if dataset is valid to plot
         if data["result"]["datasets"][0]["values"]==None:
            QMessageBox.information( self.iface.mainWindow(),"Info", "There are no datasets for this coordinates!\n\nLongitude = "+str(point.x())+", Latitude: "+str(point.y()))
            return False
            
         # Process dates 
         timeline = self.transform_dates(data["result"]["timeline"])
         value = self.compute_pre_processing(data["result"]["datasets"][0])
         longitude = data["result"]["center_coordinates"]["longitude"]
         latitude  = data["result"]["center_coordinates"]["latitude"]
         return timeline, value, longitude, latitude
    
    
    def plotTimeSeries(self):
        plt.close()
 
        coordinatesString = self.dlg.ui.lineEdit_coordinates.displayText()
        #self.dlg.setTextBrowser(str(coordinatesString))
        
        if coordinatesString=="":
           #self.dlg.setTextBrowser(  str("Missing a dataset. Please select one or more datasets.")  ) 
           QMessageBox.information( self.iface.mainWindow(),"Info", "Missing coordinates. \nPlease either type longitude,latitude or click on the map!" )
           return None
        
        # Get coordinates
        x = float(coordinatesString.split(',', 1 )[0])
        y = float(coordinatesString.split(',', 1 )[1])
        point = QgsPoint(x,y)
        
        # Get selected coverage list
        items = self.dlg.ui.listWidget_datasets.selectedItems()
        if not(items):
           #self.dlg.setTextBrowser(  str("Missing a dataset. Please select one or more datasets.")  ) 
           QMessageBox.information( self.iface.mainWindow(),"Info", "Missing dataset. \nPlease select one or more datasets." )
           return None
        
        # Create plot for each selected coverage
        for i in list(items):
            timeline, value, longitude, latitude = self.getTimeSeries(i, point)
            plt.plot(timeline, value, '-', linewidth=1, label=str(i.text()))
            
                 
        ## Make plot visible
        plt.xlabel("time")
        plt.ylabel("Value")
        plt.ylim(0, 1)
        plt.title("Pixel center coordinates (longitude,latitude): "+str(longitude)+", "+str(latitude))
        plt.legend()
        plt.grid(True)
                
        ## Maximize window plot
        figManager = plt.get_current_fig_manager()
        figManager.window.showMaximized()
        
        ## Plot results
        plt.show()
        point = QgsPoint(longitude, latitude)
        self.drawPoint(point)
        
        #self.dlg.clearTextBrowser()
        #self.dlg.setTextBrowser( str("The plot button allows to plot the the time series for the same coordinates selecting a different product and datasets.") )
        #QMessageBox.information( self.iface.mainWindow(),"Info", "X,Y = %s,%s" % (str(point.x()),str(point.y())) )


    # Run method
    def run(self):
        self.cLayer = self.iface.mapCanvas().currentLayer()
        if self.cLayer: self.provider = self.cLayer.dataProvider()
        self.canvas.setMapTool(self.clickTool)

        # show the dialog
        self.dlg.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.dlg.show()
        result = self.dlg.exec_()
        if result == 1:
            plt.close()
            self.initFields()
            