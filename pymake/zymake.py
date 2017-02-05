#!/usr/bin/python3 -u
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

#from joblib import Parallel, delayed
import multiprocessing
import sys

from .frontend.frontend_io import make_forest_path, make_forest_runcmd, make_forest_conf
from .frontend.manager import ModelManager, FrontendManager
from .expe.spec import _spec_; _spec = _spec_()

def Zymake(spec):
    commands = make_forest_conf(spec)
    if len(commands) == 1:
        frontend = FrontendManager.get(commands[0], load=True)
        model = ModelManager(commands[0])
        return frontend, model
    else:
        raise NotImplementedError('Multiple expe handle')

if __name__ == '__main__':

    from util.argparser import argparser
    zyvar = argparser.zymake()

    ### Makes OUT Files
    if zyvar['OUT_TYPE'] == 'runcmd':
        source_files = make_forest_runcmd(zyvar['SPEC'])
    elif zyvar['OUT_TYPE'] == 'path':
        source_files = make_forest_path(zyvar['SPEC'], zyvar['FTYPE'], status=zyvar['STATUS'])
    elif zyvar['OUT_TYPE'] == 'list':
        print (_spec.repr())
        exit()
    else:
        raise NotImplementedError('zymake options unknow')


    ### Makes figures on remote / parallelize
    #num_cores = int(multiprocessing.cpu_count() / 4)
    #results_files = Parallel(n_jobs=num_cores)(delayed(expe_figures)(i) for i in source_files)
    ### ...and Retrieve the figure

    print('zymake request : %s\n  %s' %(zyvar.get('request'),  zyvar['SPEC']), file=sys.stderr)
    print( '\n'.join(source_files))

