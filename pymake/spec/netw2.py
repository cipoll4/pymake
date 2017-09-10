
# -*- coding: utf-8 -*-

from pymake import ExpSpace, ExpTensor, Corpus, ExpDesign

__plot_font_size = 14

### PLOTLIB CONFIG
import matplotlib.pyplot as plt
plt.rc('font', size=__plot_font_size)  # controls default text sizes

class Netw2(ExpDesign):

    _name = 'Networks Design'

    # Use for Name on figure and table
    _mapname = dict((
        ('propro'   , 'Protein')  ,
        ('blogs'    , 'Blogs')    ,
        ('euroroad' , 'Euroroad') ,
        ('emaileu'  , 'Emaileu') ,
        ('manufacturing'  , 'Manufacturing'),
        ('fb_uc'          , 'UC Irvine' ),
        ('generator7'     , 'Network1' ),
        ('generator12'    , 'Network2' ),
        ('generator10'    , 'Network3' ),

        ('generator4'     , 'Network4' ),
        #('generator4'     , 'Network2' ),
        ('pmk.ilfm_cgs'     , 'ILFM' ),
        ('pmk.immsb_cgs'     , 'IMMSB' ),
    ))

    corpus_real_net = Corpus(['manufacturing', 'fb_uc','blogs', 'emaileu', 'propro', 'euroroad'])

    corpus_text_all = Corpus(['kos', 'nips12', 'nips', 'reuter50', '20ngroups']) # lucene

    debug_scvb = ExpTensor (
        corpus        = ['manufacturing', 'clique6'],
        model         = ['immsb_scvb', 'immsb_csg', 'mmsb_cgs', 'ilfm_cgs']  ,
        K             = 6    ,
        N             = 'all'   ,
        chunk = 25,
        iterations    = 10,
        hyper         = 'fix',
        testset_ratio = 10,

        _data_type    = 'networks',
        _refdir       = 'debug_scvb' ,
        _format       = '{model}_{K}_{chunk}_{hyper}_{homo}_{N}_{testset_ratio}'
        # push _typo_csv
    )

    # compare perplexity and rox curve from those baseline.
    compare_scvb = ExpTensor (
        corpus        = ['clique6'],
        model         = ['immsb_csg', 'ilfm_cgs']  ,
        K             = 6    ,
        N             = '100'   ,
        chunk = 10,
        iterations    = 100,
        hyper         = 'auto',
        testset_ratio = 10,

        _data_type    = 'networks',
        _refdir       = 'debug_scvb' ,
        _format       = '{model}_{K}_{chunk}_{hyper}_{homo}_{N}_{testset_ratio}'
        # push _typo_csv
    )
