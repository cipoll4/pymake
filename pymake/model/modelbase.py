# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime
import logging
lgg = logging.getLogger('root')

import numpy as np
from scipy.special import gammaln
from numpy.random import dirichlet, gamma, poisson, binomial, beta

from util.math import lognormalize, categorical

try:
    import sympy as sym
    from sympy.functions.combinatorial.numbers import stirling
except:
    pass
#import sppy

try:
    from util.compute_stirling import load_stirling
    _stirling_mat = load_stirling()
except:
    lgg.error('strling.npy file not found, passing...')


#
# TODO
# * add Likelihood base class here.
# * SVB
#


class ModelBase(object):
    """"  Root Class for all the Models.

    * Suited for unserpervised model
    * Virtual methods for the desired propertie of models
    """
    default_settings = {
        'snapshot_interval' : 100, # UNUSED
        'write' : False,
        'output_path' : 'tm-output',
        'csv_typo' : None,
        'fmt' : None,
        'iterations' : 1
    }
    def __init__(self, **kwargs):
        """ Model Initialization strategy:
            1. self lookup from child initalization
            2. kwargs lookup
            3. default value
        """

        # change to semantic -> update value (t+1)
        self.samples = [] # actual sample
        self._samples    = [] # slice to save

        for k, v in self.default_settings.items():
            self._init(k, kwargs, v)

        if self.output_path and self.write:
            import os
            bdir = os.path.dirname(self.output_path)
            fn = os.path.basename(self.output_path)
            try: os.makedirs(bdir)
            except: pass
            self.fname_i = bdir + '/inference-' + fn.split('.')[0]
            self._f = open(self.fname_i, 'wb')
            self._f.write((self.csv_typo + '\n').encode('utf8'))

        # Why this the fuck ? to remove
        #super(ModelBase, self).__init__()

    def _init(self, key, kwargs, default):
        if hasattr(self, key):
            value = getattr(self, key)
        elif key in kwargs:
            value = kwargs[key]
        else:
            value = default

        return setattr(self, key, value)

    def write_some(self, samples, buff=20):
        """ Write data with buffer manager """
        f = self._f
        fmt = self.fmt

        if samples is None:
            buff=1
        else:
            self._samples.append(samples)

        if len(self._samples) >= buff:
            #samples = np.array(self._samples)
            samples = self._samples
            np.savetxt(f, samples, fmt=str(fmt))
            f.flush()
            self._samples = []

    # try on output_path i/o error manage fname_i
    def load_some(self, iter_max=None):
        filen = self.fname_i
        with open(filen) as f:
            data = f.read()

        data = filter(None, data.split('\n'))
        if iter_max:
            data = data[:iter_max]
        # Ignore Comments
        data = [re.sub("\s\s+" , " ", x.strip()) for l,x in enumerate(data) if not x.startswith(('#', '%'))]

        #ll_y = [row.split(sep)[column] for row in data]
        #ll_y = np.ma.masked_invalid(np.array(ll_y, dtype='float'))
        return data

    def close(self):
        if not hasattr(self, '_f'):
            return
        # Write remaining data
        if self._samples:
            self.write_some(None)
        self._f.close()

    def similarity_matrix(self, theta=None, phi=None, sim='cos'):
        if theta is None:
            theta = self.theta
        if phi is None:
            phi = self.phi

        features = theta
        if sim in  ('dot', 'latent'):
            sim = np.dot(features, features.T)
        elif sim == 'cos':
            norm = np.linalg.norm(features, axis=1)
            sim = np.dot(features, features.T)/norm/norm.T
        elif sim in  ('model', 'natural'):
            sim = features.dot(phi).dot(features.T)
        else:
            lgg.error('Similaririty metric unknow: %s' % sim)
            sim = None

        if hasattr(self, 'normalization_fun'):
            sim = self.normalization_fun(sim)
        return sim

    def get_params(self):
        if hasattr(self, 'theta') and hasattr(self, 'phi'):
            return self.theta, self.phi
        else:
            return self.reduce_latent()

    def purge(self):
        """ Remove variable that are non serializable. """
        return

    def update_hyper(self):
        lgg.error('no method to update hyperparams')
        return

    def get_hyper(self):
        lgg.error('no method to get hyperparams')
        return

    # Just for MCMC ?():
    def generate(self):
        raise NotImplementedError
    def predict(self):
        raise NotImplementedError
    def get_clusters(self):
        raise NotImplementedError


def mmm(fun):
    # Todo / wrap latent variable routine
    return fun

class GibbsSampler(ModelBase):
    ''' Implmented method, except fit (other?) concerns MMM type models :
        * LDA like
        * MMSB like

        but for other (e.g IBP based), method has to be has to be overloaded...
        -> use a decorator @mmm to get latent variable ...
    '''
    def __init__(self, sampler,  **kwargs):
        self.s = sampler
        super(GibbsSampler, self).__init__(**kwargs)

    @mmm
    def measures(self):
        pp = self.evaluate_perplexity()
        if self.data_t is not None:
            pp_t = self.predictive_likelihood()
        else:
            pp_t = np.nan
        k = self.s.zsampler._K
        alpha_0 = self.s.zsampler.alpha_0
        try:
            gmma = self.s.betasampler.gmma
            alpha = np.exp(self.s.zsampler.log_alpha_beta)
        except:
            gmma = np.nan
            alpha = np.exp(self.s.zsampler.logalpha)

        alpha_mean = alpha.mean()
        alpha_var = alpha.var()
        delta_mean = self.s.zsampler.likelihood.delta.mean()
        delta_var = self.s.zsampler.likelihood.delta.var()

        measures = [pp, pp_t, k, alpha_0, gmma, alpha_mean, delta_mean, alpha_var, delta_var]
        return measures


    def fit(self):
        time_it = 0
        self.evaluate_perplexity()
        for i in range(self.iterations):
            ### Output / Measures
            print('.', end='')
            measures = self.measures()
            sample = [i, time_it] + measures
            k = self.s.zsampler._K
            lgg.info('Iteration %d, K=%d Entropy: %s ' % (i, k, measures[0]))
            if self.write:
                self.write_some(sample)

            begin = datetime.now()
            ### Sampling
            self.s.sample()
            time_it = (datetime.now() - begin).total_seconds() / 60

            if i >= self.iterations:
                s.clean()
                break
            if i >= self.burnin:
                if i % self.thinning == 0:
                    self.samples.append([self._theta, self._phi])

        print()
        ### Clean Things
        self.samples = self.samples
        if not self.samples:
            self.samples.append([self._theta, self._phi])
        self.close()
        return

    @mmm
    def likelihood(self, theta=None, phi=None):
        if theta is None:
            theta = self.theta
        if phi is None:
            phi = self.phi
        likelihood = theta.dot(phi).dot(theta.T)
        return likelihood

    @mmm
    def update_hyper(self, hyper):
        if hyper is None:
            return
        elif isinstance(type(hyper), (tuple, list)):
            alpha = hyper[0]
            gmma = hyper[1]
            delta = hyper[2]
        else:
            delta = hyper.get('delta')
            alpha = hyper.get('alpha')
            gmma = hyper.get('gmma')

        if delta:
            self._delta = delta
        if alpha:
            self._alpha = alpha
        if gmma:
            self._gmma = gmma

    @mmm
    def get_hyper(self):
        if not hasattr(self, '_alpha'):
            try:
                self._delta = self.s.zsampler.likelihood.delta
                if type(self.s) is NP_CGS:
                    self._alpha = self.s.zsampler.alpha_0
                    self._gmma = self.s.betasampler.gmma
                else:
                    self._alpha = self.s.zsampler.alpha
                    self._gmma = None
            except:
                lgg.error('Need to propagate hyperparameters to BaseModel class')
                self._delta = None
                self._alpha = None
                self._gmma =  None
        return self._alpha, self._gmma, self._delta

    # Nasty hack to make serialisation possible
    @mmm
    def purge(self):
        try:
            self.s.mask = self.s.zsampler.likelihood.data_ma.mask
        except:
            pass

        self.s.zsampler.betasampler = None
        self.s.zsampler._nmap = None
        self.s.msampler = None
        self.s.betasampler = None
        self.s.zsampler.likelihood = None

    @mmm
    def evaluate_perplexity(self, data=None):
        self._theta, self._phi = self.s.zsampler.estimate_latent_variables()
        return self.s.zsampler.perplexity(data)

    # keep only the most representative dimension (number of topics) in the samples
    @mmm
    def reduce_latent(self):
        theta, phi = list(map(list, zip(*self.samples)))
        ks = [ mat.shape[1] for mat in theta]
        bn = np.bincount(ks)
        k_win = np.argmax(bn)
        lgg.debug('K selected: %d' % k_win)

        ind_rm = []
        [ind_rm.append(i) for i, v in enumerate(theta) if v.shape[1] != k_win]
        for i in sorted(ind_rm, reverse=True):
            theta.pop(i)
            phi.pop(i)

        lgg.debug('Samples Selected: %d over %s' % (len(theta), len(theta)+len(ind_rm) ))

        self.theta = np.mean(theta, 0)
        self.phi = np.mean(phi, 0)
        self.K = self.theta.shape[1]
        return self.theta, self.phi


### Base Sampler

class MSampler(object):

    def __init__(self, zsampler):
        self.stirling_mat = _stirling_mat
        self.zsampler = zsampler
        self.get_log_alpha_beta = zsampler.get_log_alpha_beta
        self.count_k_by_j = zsampler.doc_topic_counts

        # We don't know the preconfiguration of tables !
        self.m = np.ones(self.count_k_by_j.shape, dtype=int)
        self.m_dotk = self.m.sum(axis=0)

    def sample(self):
        self._update_m()

        indices = np.ndenumerate(self.count_k_by_j)

        lgg.info( 'Sample m...')
        for ind in indices:
            j, k = ind[0]
            count = ind[1]

            if count > 0:
                # Sample number of tables in j serving dishe k
                params = self.prob_jk(j, k)
                sample = categorical(params) + 1
            else:
                sample = 0

            self.m[j, k] = sample

        self.m_dotk = self.m.sum(0)
        self.purge_empty_tables()

        return self.m

    def _update_m(self):
        # Remove tables associated with purged topics
        for k in sorted(self.zsampler.last_purged_topics, reverse=True):
            self.m = np.delete(self.m, k, axis=1)

        # Passed by reference, but why not...
        self.count_k_by_j = self.zsampler.doc_topic_counts
        K = self.count_k_by_j.shape[1]
        # Add empty table for new fancy topics
        new_k = K - self.m.shape[1]
        if new_k > 0:
            lgg.info( 'msampler: %d new topics' % (new_k))
            J = self.m.shape[0]
            self.m = np.hstack((self.m, np.zeros((J, new_k), dtype=int)))

    # Removes empty table.
    def purge_empty_tables(self):
        # cant be.
        pass

    def prob_jk(self, j, k):
        # -1 because table of current sample topic jk, is not conditioned on
        njdotk = self.count_k_by_j[j, k]
        if njdotk == 1:
            return np.ones(1)

        possible_ms = np.arange(1, njdotk) # +1-1
        log_alpha_beta_k = self.get_log_alpha_beta(k)
        alpha_beta_k = np.exp(log_alpha_beta_k)

        normalizer = gammaln(alpha_beta_k) - gammaln(alpha_beta_k + njdotk)
        log_stir = self.stirling_mat[njdotk, possible_ms]
        #log_stir = sym.log(stirling(njdotk, m, kind=1)).evalf() # so long.

        params = normalizer + log_stir + possible_ms*log_alpha_beta_k

        return lognormalize(params)

class BetaSampler(object):

    def __init__(self, gmma, msampler):
        self.gmma = gmma
        self.msampler = msampler

        # Initialize restaurant with just one table.
        self.beta = dirichlet([1, gmma])

    def sample(self):
        lgg.info( 'Sample Beta...')
        self._update_dirichlet_params()
        self.beta = dirichlet(self.dirichlet_params)

        return self.beta

    def _update_dirichlet_params(self):
        m_dotk_augmented = np.append(self.msampler.m_dotk, self.gmma)
        lgg.info( 'Beta Dirichlet Prior: %s, alpha0: %.4f ' % (m_dotk_augmented, self.msampler.zsampler.alpha_0))
        self.dirichlet_params = m_dotk_augmented

