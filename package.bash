#!/bin/bash
###########################################################################
#                                                                         #
#   This program is free software; you can redistribute it and/or modify  #
#   it under the terms of the GNU General Public License as published by  #
#   the Free Software Foundation; either version 2 of the License, or     #
#   (at your option) any later version.                                   #
#                                                                         #
###########################################################################

set -e
cd res1d_loader
pyrcc5 -o resources.py resources.qrc
cd ..

rm -f qgis-res1d-plugin.zip && cd res1d_loader && git archive --prefix=res1d_loader/ -o ../qgis-res1d-plugin.zip HEAD

