# qgis-res1d-plugin

## Install

### Mikeio1d package

The minimal version of QGIS for this plugin is QGIS 3.22, that works with Python 3.9. 
To read res1d files, this plugin needs the package mikeio1d [[mikeio1d|https://github.com/DHI/mikeio1d]] . Installing this package from PyPi is only supported for Python 3.8 or previous. But it is possible to install the development version of this package. 

To install this package in the QGIS environement:

- Open the osgeo4w shell from the start menu of Windows

- Enter the following commands:

`pip install setuptools`

`pip install wheel`

`pip install https://github.com/DHI/mikeio1d/archive/main.zip`

