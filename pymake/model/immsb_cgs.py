# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals


from pymake.model.hdp.mmsb import GibbsRun, Likelihood, ZSampler, MSampler, BetaSampler, NP_CGS

# @idem than ilda_cgs
class immsb_cgs(GibbsRun):
    def __init__(self, expe, frontend):

        delta = expe.hyperparams.get('delta',1)
        alpha = expe.hyperparams.get('alpha',1)
        gmma = expe.hyperparams.get('gmma',1)

        hyper = expe.hyper
        assortativity = expe.get('homo')
        hyper_prior = expe.get('hyper_prior') # HDP hyper optimization
        K = expe.K

        try:
            data = frontend.data_ma
            data_t = frontend.data_t
        except:
            data = data_t = None

        likelihood = Likelihood(delta, data, assortativity=assortativity)

        # Nonparametric case
        zsampler = ZSampler(alpha, likelihood, K_init=K, data_t=data_t)
        msampler = MSampler(zsampler)
        betasampler = BetaSampler(gmma, msampler)
        jointsampler = NP_CGS(zsampler, msampler, betasampler,
                              hyper=hyper, hyper_prior=hyper_prior)

        super(immsb_cgs, self).__init__(jointsampler,
                                    iterations=expe.iterations,
                                    output_path=expe.output_path,
                                    write=expe.write,
                                    data_t=data_t)
        self.update_hyper(expe.hyperparams)
