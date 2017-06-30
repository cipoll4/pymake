# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import  os
if os.environ.get('DISPLAY') is None:
    import matplotlib; matplotlib.use('Agg')


# This lines take a while
from pymake.expe.format import Corpus, Model, Script, ExpSpace, ExpVector, ExpTensor, ExpeFormat, ExpDesign
from pymake.expe.gramexp import GramExp

from pymake.frontend.frontend_io import SpecLoader
#__spec = SpecLoader._default_spec()
__spec = SpecLoader.get_atoms()

from pymake.frontend.frontendtext import frontendText
from pymake.frontend.frontendnetwork import frontendNetwork
from pymake.frontend.manager import ModelManager, FrontendManager



#
# Erckelfault
#

#''' PRELOAD LIB '''
#import importlib
#_MODULES = ['community',
#            ('networkx', 'nx'),
#            ('numpy', 'np'),
#            ('scipy', 'sp'),
#            ('matplotlib.pyplot', 'plt')
#           ]
#
#for m in _MODULES:
#    try:
#        if type(m) is tuple:
#            mn = m[1]
#            m = m[0] if type(m) is tuple else m
#        else:
#            mn = m
#        globals()[mn] = importlib.import_module(m)
#    except ImportError:
#        print("* module `%s' unavailable" % (m))
#
