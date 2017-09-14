# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import sys, os
import re
import logging
import operator
import fnmatch
import pickle
import subprocess
import inspect, traceback, importlib
from collections import defaultdict
from itertools import product
from functools import reduce, wraps
from copy import deepcopy
import numpy as np

import argparse

from pymake import  ExpTensor, ExpSpace, ExpeFormat, Model, Corpus, Script, ExpVector
from pymake.util.utils import colored, basestring, get_global_settings

import pymake.frontend.frontend_io as mloader

from pymake.frontend.frontend_io import _DATA_PATH, ext_status, is_empty_file


''' Grammar Expe '''
_version = 0.1
lgg = logging.getLogger('root')

# Custom formatter
# From : https://stackoverflow.com/questions/14844970/modifying-logging-message-format-based-on-message-logging-level-in-python3
class MyLogFormatter(logging.Formatter):

    critical_fmt  = "====>>> CRITICAL: %(msg)s"
    err_fmt  = "===>> ERROR: %(msg)s"
    warn_fmt  = "==> Warning: %(msg)s"
    #info_fmt = '%(module): %(msg)s'
    #info_fmt = '%(levelno)d: %(msg)s'
    default_fmt = '%(msg)s'

    # CUstom Level
    VDEBUG_LEVEL_NUM = 9
    logging.addLevelName(VDEBUG_LEVEL_NUM, "VDEBUG")
    logging.VDEBUG = 9

    def __init__(self, fmt=default_fmt):
        super().__init__(fmt=fmt, datefmt=None, style='%')

    def format(self, record):

        # Save the original format configured by the user
        # when the logger formatter was instantiated
        format_orig = self._style._fmt

        # Replace the original format with one customized by logging level
        if record.levelno == logging.WARNING:
            self._style._fmt = MyLogFormatter.warn_fmt
        elif record.levelno == logging.ERROR:
            self._style._fmt = MyLogFormatter.err_fmt
        elif record.levelno == logging.CRITICAL:
            self._style._fmt = MyLogFormatter.critical_fmt
        else:
            self._style._fmt = MyLogFormatter.default_fmt


        # Call the original formatter class to do the grunt work
        result = logging.Formatter.format(self, record)

        # Restore the original format configured by the user
        self._style._fmt = format_orig

        return result


def setup_logger(level=logging.INFO, name='root'):
    #formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

    if level == 1:
        level = logging.DEBUG
    elif level == 2:
        level = logging.VDEBUG
    elif level == 3:
        print ('what level of verbosity heeere ?')
        exit(2)
    elif level == -1:
        level = logging.WARNING
    else:
        # make a --silent option for juste error and critial log ?
        level = logging.INFO

    # Get logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Format handler
    handler = logging.StreamHandler(sys.stdout)
    #handler.setFormatter(logging.Formatter(fmt=fmt))
    handler.setFormatter(MyLogFormatter())

    # Set Logger
    logger.addHandler(handler)
    # Prevent logging propagation of handler,
    # who reults in logging things multiple times
    logger.propagate = False


    def vdebug(self, message, *args, **kws):
        # Yes, logger takes its '*args' as 'args'.
        if self.isEnabledFor(logging.VDEBUG):
            self._log(logging.VDEBUG, message, args, **kws)

    #logger.Logger.vdebug = vdebug
    logging.Logger.vdebug = vdebug

    return logger



class GramExp(object):
    ''' Create a mapping between different format of design of experiments.

        Attribute
        ---------
        exp_tensor :ExpTensor
            tensor of experiments

        Methods
        -------
        __init__ : conf choice in :
           * Expe -> One experiments
           * ExpTensor -> Design of experiments
           * Expe & spec in Expe -> Design of experiments with global value,
                either from conf or command-line args.
                conf value will udpdate all experiments first from command-line
                argument then from defaut values.

        Notes
        -----

        Design of Experiments can take three forms :
        1. command-line arguments (see self.parsearg).
            * use for parralization with Gnu parallel.
        2. Expe : Uniq experiments specificattion,
            * @Todo list of Expe
        3. ExpTensor : Represente a tensor of experiments.
           Each entry of the dict contains an iterable over specifications
           for this entry. (see frontend.frontend_io)
           * @Todo pass rule to filter experiments...

        ### Expe Filtering
        Expe can contains **special** keywords and value :
        * _bind rules : List of rules of constraintsi on the design.
            * Inclusif rules
                + [a.b]  --- a(value) shoudld occur only with b(value), (ie 'lda.fast_init')
                + [a.b.c] --- with a(value), key b(key) take only c (value), (ie 'lda.iterations.100')
            * Exclusif Rules
                + [a.!b]  --- a(value) shoudld not only with b(value),
                + [a.b.!c] --- with a(value), key b(key) don't take c (value),

            Warning : it does only check the last words when parameter are
                      separated by a dot (.) as for model module (name pmk.lda !) for example.

        * if an attribute  take the value "_null",
          then it will be removed from the Exp. This can be usefull when piping
          ouptuf of pymake to some script to parallelize.

        ### I/O Concerns
        An experiment typically write three kind of files :
        Corpus are load/saved using Pickle format in:
        * bdir/corpus_name.pk
        Models are load/saved using pickle/json/cvs in :
        * bdir/refdir/rep/model_name_parameters.pk   <--> ModelManager
        * bdir/refir/rep/model_name_parameters.json <--> DataBase
        * bdir/refdir/rep/model_name_parameters.inf  <--> ModelBase

    '''
    _examples = '''Examples:
        >> Text fitting
        fit.py -k 6 -m ldafullbaye -p
        >> Network fitting :
        fit.py -m immsb -c alternate -n 100 -i 10'''

    # has special semantics
    _special_keywords = [ 'refdir', '_base_type',
                         '_format', '_csv_typo',
                         '_repeat',
                        ] # output_path => pmk-basedire/{base_type}/{refdir}/{repeat}/${format}:${csv_typo}

    # Reserved by GramExp
    # shloud ne in special ?
    _reserved_keywords = ['_spec', # for nested specification
                          '_id_expe', # unique expe identifier
                         ]


    _exp_default = {
        #'host'      : 'localhost',
        'verbose'   : logging.INFO,
        '_load_data' : True, # if .pk corpus is here, load it.
        '_save_data' : False,
        'write'     : False,
    }

    def __init__(self, conf, usage=None, parser=None, parseargs=True):
        # @logger One logger by Expe ! # in preinit
        setup_logger(level=conf.get('verbose'))
        self._spec = mloader.SpecLoader.default_spec()

        if conf is None:
            conf = {}

        if parseargs is True:
            kwargs, self.argparser = self.parseargsexpe(usage)
            conf.update(kwargs)
        if parser is not None:
            # merge parser an parsargs ?
            self.argparser = parser

        [conf.update({k:v}) for k,v in self._exp_default.items() if k not in conf]
        conf = deepcopy(conf)

        # Set expTensor init.
        self._user_spec = conf.get('_spec', {})

        # Make main data structure
        self.exp_tensor = ExpTensor.from_expe(conf, parser=self.argparser)
        self.checkExp(self.exp_tensor)
        self.exp_setup()

    def _preprocess_exp(self):
        # @improvment: do filter from spec
        exp = self.exp_tensor
        size_exp = np.prod([len(x) for x in exp.values()])

        self._check_bind(exp)
        self._check_model_typo(exp)
        self._check_null(exp)

        if size_exp > 1 and 'write' in exp:
            self._check_format(exp)

        # Clean pymake extra args:
        extra_args = ['_ignore_format_unique', ('_net', False)]
        keys_to_remove = []
        for _key in extra_args:
            if type(_key) is tuple:
                if self._conf.get(_key[0]) is _key[1]:
                    keys_to_remove.append(_key[0])
            elif _key in self._conf:
                    keys_to_remove.append(_key)
        # |
        for key in keys_to_remove:
            self._conf.pop(key)
            self.exp_tensor.pop(key)


    @staticmethod
    def _check_model_typo(exp_tensor):
        ''' Assume default module is pymake '''
        models = exp_tensor.get('model', [])
        for i, m in enumerate(models):
            if not '.' in m:
                models[i] = 'pmk.%s'%(m)

    def _check_bind(self, exp_tensor):
        ''' Rules Filter '''
        if '_bind' in exp_tensor:
            self._bind = exp_tensor.pop('_bind')
            if not isinstance(self._bind, list):
                self._bind = [self._bind]
        else:
            self._bind = getattr(self, '_bind', [])

    def _check_null(self, exp_tensor):
        ''' Filter _null '''
        for k in exp_tensor.copy():
            if '_null' in exp_tensor.get(k, []):
                exp_tensor.pop(k)
                _null = getattr(self, '_null',[])
                _null.append(k)

    def _check_format(self, exp_tensor):
        ''' Check if all expVector are distinguishable in _format. '''
        hidden_key = []
        _format = exp_tensor.get('_format', [''])
        if len(_format) > 1:
            raise NotImplementedError('multiple _format not implemented')
        else:
            _format = _format[0]

        format_settings = re.findall(r'{([^{}]*)}', _format)
        for setting, values in exp_tensor.items():
            if isinstance(values, list) and len(values) > 1 and setting not in format_settings:
                hidden_key.append(setting)

        if hidden_key and self._conf.get('_ignore_format_unique') is not True:
            lgg.error('The following settings are not set in _format:')
            print(' '+ '  '.join(hidden_key))
            print('Possible conflicts in experience results outputs.')
            print('Please correct {_format} key to fit the experience settings.')
            print('To force the runs, use:  --ignore-format-unique')
            print('Exiting...')
            exit(2)

    @classmethod
    def checkExp(cls, exp):
        ''' check format and rules of exp_tensor '''

        # check reserved keyword are absent from exp
        for m in cls._reserved_keywords:
            if m in exp:
                raise ValueError('%m is a reserved keyword of gramExp.')

        # Format
        assert(isinstance(exp, ExpTensor))
        for k, v in exp.items():
            if not issubclass(type(v), (list, tuple, set)):
                raise ValueError('error, exp value should be iterable: %s' % k, v)


    def make_tensor(self, lod):
        exp_tensor = ExpTensor()
        for d in lod:
            exp_tensor.push_dict(d)

        return exp_tensor

    def make_lod(self, exp):
        ''' Make a list of Expe from tensor, with filtering '''

        lod = self.make_forest_conf(exp)

        # POSTFILTERING
        # Bind Rules
        idtoremove = []
        for expe_id, d in enumerate(lod):
            for rule in self._bind:
                _bind = rule.split('.')
                values = list(d.values())

                # This is only for  last dot separator process
                for j, e in enumerate(values):
                    if type(e) is str:
                        values[j] = e.split('.')[-1]


                if len(_bind) == 2:
                    # remove all occurence if this bind don't occur
                    # simltaneous in each expe.
                    a, b = _bind
                    if b.startswith('!'):
                        # Exclusif Rule
                        b = b[1:]
                        if a in values and b in values:
                            idtoremove.append(expe_id)
                    else:
                        # Inclusif Rule
                        if a in values and not b in values:
                            idtoremove.append(expe_id)

                elif len(_bind) == 3:
                    # remove occurence of this specific key:value if
                    # it does not comply with this bind.
                    a, b, c = _bind
                    # Get the type of this key:value.
                    _type = type(d[b])
                    if _type is bool:
                        _type = lambda x: True if x in ['True', 'true', '1'] else False

                    if c.startswith('!'):
                        # Exclusif Rule
                        c = c[1:]
                        if a in values and _type(c) == d[b]:
                            idtoremove.append(expe_id)
                    else:
                        # Inclusif Rule
                        if a in values and _type(c) != d[b]:
                            idtoremove.append(expe_id)

        lod = [d for i,d in enumerate(lod) if i not in idtoremove]

        # add extra information in lod expes
        for _id,  expe in enumerate(lod):
            expe['_id_expe'] = _id

        return lod

    def set_default_expe(self, def_conf):
        for k, v in def_conf.items():
            if not k in self.exp_tensor:
                self.exp_tensor[k] = [v]
                self._conf[k] = v
                for expe in self.lod:
                    expe[k] = v

    # @obsolete
    def update(self, **kwargs):
        self._conf.update(kwargs)
        self.exp_tensor.update_from_dict(kwargs)

        for d in self.lod:
            d.update(kwargs)

    # @Debug self.lod is left untouched...
    def remove(self, k):
        if k in self._conf:
            self._conf.pop(k)
        if k in self.exp_tensor:
            self.exp_tensor.pop(k)
        for d in self.lod:
            if k in d:
                d.pop(k)

    def exp_setup(self, exp=None):
        if exp is not None:
            self.exp_tensor = exp

        # Global settings (unique argument)
        self._conf = {k:v[0] for k,v in self.exp_tensor.items() if len(v) == 1}

        # makes it contextual.
        self._preprocess_exp()

        # Make lod
        self.lod = self.make_lod(self.exp_tensor)


    def getConfig(self):
        # get global conf...
        raise NotImplementedError

    def getCorpuses(self):
        return self.exp_tensor.get('corpus', [])

    def getModels(self):
        return self.exp_tensor.get('model',[])

    def get(self, key, default=None):
        return self.exp_tensor.get(key, default)

    def __len__(self):
        #return reduce(operator.mul, [len(v) for v in self.exp_tensor.values()], 1)
        return len(self.lod)

    @staticmethod
    def make_forest_conf(dol_spec):
        """ Make a list of config/dict.
            Convert a dict of list to a list of dict.
        """
        if len(dol_spec) == 0:
            return []

        len_l = [len(l) for l in dol_spec.values()]
        keys = sorted(dol_spec)
        lod = [dict(zip(keys, prod)) for prod in product(*(dol_spec[key] for key in keys))]

        return lod

    @staticmethod
    def make_forest_path(lod, _type, status='f', full_path=False):
        """ Make a list of path from a spec/dict, the filename are
            oredered need to be align with the get_from_conf_file.

            *args -> make_output_path
        """
        targets = []
        for spec in lod:
            filen = GramExp.make_output_path(spec, _type, status=status)
            if filen:
                s = filen.find(_DATA_PATH)
                pt = 0
                if not full_path and s >= 0:
                    pt = s + len(_DATA_PATH)
                targets.append(filen[pt:])
        return targets

    @classmethod
    def make_output_path(cls, expe, _type=None, status=None, base_dir='results'):
        """ Make a single output path from a expe/dict
            @status: f finished
            @type: pk, json or inference.
        """
        expe = defaultdict(lambda: None, expe)
        filen = None
        base = expe.get('_data_type', 'pmk-temp')
        hook = expe.get('_refdir', '')

        basedir = os.path.join(os.path.dirname(__file__), _DATA_PATH, base, base_dir)

        if '_repeat' in expe and ( expe['_repeat'] is not None and expe['_repeat'] is not False):
            p = os.path.join(hook, str(expe['_repeat']))
        else:
            p = os.path.join(hook)

        if not expe['_format']:
            # or give a hash if write is False ?
            lgg.error('No _format given, please set _format for output_path settings.')
            exit(2)

        t = expe['_format'].format(**cls.get_file_format(expe))

        filen = os.path.join(basedir, p, t)

        ext = ext_status(filen, _type)
        if ext:
            filen = ext

        if status is 'f' and is_empty_file(filen):
            return  None
        else:
            return filen

    @classmethod
    def make_input_path(cls, expe, _type=None, status=None, base_dir='training'):
        """ Make a single input path from a expe/dict
        """
        expe = defaultdict(lambda: None, expe)
        filen = None
        base = expe.get('_data_type', 'pmk-temp')

        # Corpus is an historical exception and has its own subfolder.
        c = expe.get('corpus')
        if not c:
            c = ''
            lgg.debug('warning: No Corpus given')
        if c.lower().startswith(('clique', 'graph', 'generator')):
            c = c.replace('generator', 'Graph')
            c = c.replace('graph', 'Graph')
            c = 'generator/' + c

        input_dir = os.path.join(os.path.dirname(__file__), _DATA_PATH, base, base_dir, c)

        return input_dir

    @staticmethod
    def get_file_format(expe):
        fmt_expe = expe.copy()
        # iteration over {expe} trow a 'RuntimeError: dictionary changed size during iteration',
        # maybe due to **expe pass in argument ?
        for k, v in fmt_expe.items():
            if isinstance(v, (list, dict)):
                fmt_expe[k] = '_id_expe' + str(expe['_id_expe'])
        return fmt_expe



    @staticmethod
    def get_parser(description=None, usage=None):
        import pymake.expe.gram as _gram
        parser = _gram.ExpArgumentParser(description=description, epilog=usage,
                                        formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument('--version', action='version', version='%(prog)s '+str(_version))

        return parser

    @staticmethod
    def push_gramarg(parser, gram=None):
        import pymake.expe.gram as _gram
        if gram is None:
            gram = _gram._Gram
        else:
            gram = importlib.import_module(gram)
            gram = next( (getattr(gram, _list) for _list in dir(gram) if isinstance(getattr(gram, _list), list)), None)

        grammar = []
        args_ = []
        for e in gram:
            if not isinstance(e, dict):
                args_.append(e)
                continue
            grammar.append((args_, e))
            args_ = []

        #[parser.add_argument(*r[0], **r[1]) for r in grammar]
        # check for duplicate
        for r in grammar:
            try:
                parser.add_argument(*r[0], **r[1])
            except argparse.ArgumentError as e:
                err_mesg = " (it'll be overwritten)"
                if r[0][0] in ('-v', '-s', '-w', '--seed'):
                    # @debug, level here is not set yet, so his not active by default.
                    # parsing difficulet becaus context sensitive (option (-v) impact how the options are interpreted)
                    lgg.debug(str(e)+err_mesg)
                else:
                    lgg.error(str(e)+err_mesg)
                #exit(3)


    @classmethod
    def parseargsexpe(cls, usage=None, args=None, parser=None):
        description = 'Specify an experimentation.'
        if not usage:
            usage = GramExp._examples

        if parser is None:
            parser = GramExp.get_parser(description, usage)
        #s, remaining = parser.parse_known_args(args=args)

        # Push pymake grmarg.
        cls.push_gramarg(parser)
        # third-party
        gramarg = get_global_settings('gramarg')
        if gramarg:
            cls.push_gramarg(parser, gramarg)

        s = parser.parse_args(args=args)

        # Assume None value are non-filled options
        settings = dict((key,value) for key, value in vars(s).items() if value is not None)
        GramExp.expVectorLookup(settings)
        return settings, parser

    @classmethod
    def zymake(cls, request={}, usage=''):
        usage ='''\
        ----------------
        Communicate with the data :
        ----------------
         |   zymake update  : update the pymake index
         |   zymake -l [expe(default)|model|script|SPEC] : (default) show available spec
         |   zymake show SPEC : show one spec details
         |   zymake run SPEC [--script [fun][*args]] ... : execute tasks (default is fit)
         |   zymake runpara SPEC [--script [fun][*args]] ...: parallelize tasks
         |   zymake hist [-n n_lines] : show command history
         |   zymake cmd SPEC ... : generate command-line
         |   zymake path SPEC Filetype(pk|json|inf) [status] ... : show output_path
        ''' + '\n' + usage

        s, parser = GramExp.parseargsexpe(usage)
        request.update(s)

        _spec = mloader.SpecLoader.default_spec()
        ontology = dict(
            _do    = ['cmd', 'show', 'path', 'burn', 'run', 'update', 'init', 'runpara', 'hist'],
            _spec   = _spec._specs(),
            _ftype = ['json', 'pk', 'inf']
        )
        ont_values = sum([w for k, w in ontology.items() if k != '_spec'] , [])

        # Init _do value.
        if not request.get('_do'):
            request['_do'] = []

        # Special Case for CLI.
        if 'script' in request:
            if request.get('do_list'):
                # if a listing is requested go through run.
                # It'll be stop after signature printing
                request['_do'] = ['run']

            # check if no command is specified, and
            # if 'script" is there, set 'run' command as default.
            do = request.get('_do', [])
            no_do = len(do) == 0
            no_do_command = len(request['_do']) > 0 and not request['_do'][0] in ontology['_do']
            if no_do or no_do_command:
                request['_do'] = ['run'] + do


        do = request.get('_do', [])
        checksum = len(do)
        # No more Complex !
        run_indexs = []
        for i, v in enumerate(do.copy()):
            if str.isdigit(v):
                run_indexs.append(int(v))
                checksum -= 1
            else:
                for ont, words in ontology.items():
                    # Walktrough the ontology to find arg meaning
                    if v in words:
                        if ont == '_spec':
                            if v in ont_values:
                                lgg.error('=> Warning: conflict between name of ExpDesign and GramExp ontology keywords ')
                            do.remove(v)
                            v = _spec[v]
                        request[ont] = v
                        checksum -= 1
                        break

        request['_run_indexs'] = run_indexs

        if request.get('_spec') and len(do) == 0:
            request['_do'] = 'show'


        if checksum != 0:
            lgg.error('==> Error : unknown argument: %s\n\nAvailable SPEC : %s' % (do, sorted(_spec._specs())))
            exit(10)
        return cls(request, usage=usage, parser=parser, parseargs=False)

    @classmethod
    def generate(cls, request={},  usage=''):
        usage = '''\
        ----------------
        Execute scripts :
        ----------------
         |   generate [method][fun][*args] [EXP]
         |
         |  -g: generative model -- evidence
         |  -p: predicted data -- model fitted
         |  --hyper-name *
         |
         ''' +'\n'+usage

        parser = GramExp.get_parser(usage=usage)
        parser.add_argument('-g', '--generative', dest='_mode', action='store_const', const='generative')
        parser.add_argument('-p', '--predictive', dest='_mode', action='store_const', const='predictive')

        s, parser = GramExp.parseargsexpe(parser=parser)

        request.update(s)

        do = request.get('_do') or ['list']
        if not isinstance(do, list):
            # Obsolete ?
            do = [do]
            request['_do'] = do

        # Update the spec is a new one is argified
        _spec = mloader.SpecLoader.default_spec()
        for a in do:
            if a in _spec.keys() and issubclass(type(_spec[a]), ExpTensor):
                request['_spec'] = _spec[a]
                do.remove(a)

        return cls(request, usage=usage, parser=parser, parseargs=False)

    @staticmethod
    def expVectorLookup(request):
        ''' set exp from spec if presents '''

        # get list of scripts/*
        # get list of method
        _spec = mloader.SpecLoader.default_spec()
        ontology = dict(
            # Allowed multiple flags keywords
            check_spec = {'corpus':Corpus, 'model':Model},
            spec = _spec.keys()
        )

        # Handle spec and multiple flags arg value
        # Too comples, better Grammat/Ast ?
        for k in ontology['check_spec']:
            sub_request = ExpVector()
            for v in request.get(k, []):
                if v in ontology['spec'] and k in ontology['check_spec']:
                    # Flag value is in specification
                    if issubclass(type(_spec[v]), ontology['check_spec'][k]):
                        sub_request.extend( _spec[v] )
                    else:
                        raise ValueError('%s not in Spec' % v)
                else:
                    # Multiple Flags
                    sub_request.extend([v])
            if sub_request:
                request[k] = sub_request

    @classmethod
    def exp_tabulate(cls, conf={}, usage=''):

        gargs = clargs.grouped['_'].all
        for arg in gargs:
            try:
                conf['K'] = int(arg)
            except:
                conf['model'] = arg
        return cls(conf, usage=usage)

    def make_commandline(self):
        commands = self.make_commands()
        commands = [' '.join(c) for c in commands]
        return commands

    def make_path(self, ftype=None, status=None, fullpath=None):
        return self.make_forest_path(self.lod, ftype, status, fullpath)


    def make_commands(self):
        lod = self.lod
        commands = []
        for e in lod:
            argback = self.argparser._actions
            command = []
            args_seen = []
            for a in argback:
                if not hasattr(a, 'option_strings') or len(a.option_strings) == 0:
                    # Assume every options of expe has a flags
                    continue
                if a.dest in e and a.dest not in args_seen:
                    #if isinstance(a, (gram.unaggregate_append,)):
                    #    # Assume except_append are removed from expe,
                    #    # special traitment
                    #    continue
                    if a.nargs == 0:
                        # standalone flags
                        store = e[a.dest]
                        if 'StoreTrue' in str(type(a)):
                            storetrue = True
                        elif 'StoreFalse' in str(type(a)):
                            storetrue = False
                        else:
                            raise ValueError('Check the Type of argparse for : %s'%e)
                        if storetrue and store:
                            command += [a.option_strings[0]]
                    else:
                        _arg = e[a.dest]
                        if isinstance(_arg, (list, set, tuple)):
                            _arg = ' '.join(_arg)
                        command += [a.option_strings[0]] + [str(_arg)]
                        args_seen.append(a.dest)

            commands.append(command)
        return commands

    def reorder_lastvalid(self, _type='pk'):
        for i, e in enumerate(self.lod):
            if self.make_output_path(e, _type=_type, status='f'):
                self.lod[-1], self.lod[i] = self.lod[i], self.lod[-1]
                break
        return

    def expname(self):
        return self.exp_tensor.name()

    def exptable(self, extra=[]):
        if self._bind:
            extra += [('_bind', self._bind)]
        return self.exp_tensor.table(extra)

    def spectable(self):
        return self._spec._table()

    def atomtable(self, _type='short'):
        return self._spec._table_atoms(_type=_type)

    def scripttable(self):
        return Script.table()

    def getSpec(self):
        return self._spec

    @staticmethod
    def Spec():
        return mloader.SpecLoader.default_spec()

    def help_short(self):
        shelp = self.argparser.format_usage() + self.argparser.epilog
        return shelp

    def simulate_short(self):
        ''' Simulation Output '''
        print('''
              Nb of experiments : %s
              Corpuses : %s
              Models : %s
              ''' % (len(self), self.getCorpuses(), self.getModels()), file=sys.stdout)
        exit()

    def simulate(self, indexs=None, halt=True, file=sys.stdout):

        if not indexs:
            indexs = range(len(self))

        self.lod = [self.lod[i] for i in indexs]
        self.exp_tensor = self.make_tensor(self.lod)

        print('-'*30, file=file)
        print('PYMAKE Request %s : %d expe' % (self.exp_tensor.name(), len(self) ), file=file)
        print(self.exptable(), file=file)
        if halt:
            exit()
        else:
            return

    @staticmethod
    def sign_nargs(fun):
        return sum([y.default is inspect._empty for x,y in inspect.signature(fun).parameters.items() if x != 'self'])

    @staticmethod
    def tb_expeformat(sandbox):
        signatures = []
        for m in dir(sandbox):
            if not callable(getattr(sandbox, m)) or m.startswith('__') or hasattr(ExpeFormat, m):
                continue
            sgn = inspect.signature(getattr(sandbox, m))
            d = [v for k,v in sgn.parameters.items() if k != 'self'] or []
            signatures.append((m, d))
        return signatures

    @staticmethod
    def functable(obj):
        ''' show method/doc associated to one class (in /scripts) '''
        lines = []
        for m in  GramExp.tb_expeformat(obj):
            name = m[0]
            opts = ['%s [%s]'% (o.name, o.default) for o in m[1] if o]
            opts = ' '.join(opts)
            line = name + ' ' + opts
            lines.append(line)
        return lines

    @staticmethod
    def load(fn, silent=False):
        # Pickle class
        fn = fn + '.pk'
        if not silent:
            lgg.info('Loading frData : %s' % fn)
        with open(fn, 'rb') as _f:
            return pickle.load(_f)

    @staticmethod
    def save(data, fn, silent=False):
        # Pickle class
        fn = fn + '.pk'
        if not silent:
            lgg.info('Saving frData : %s' % fn)
        with open(fn, 'wb') as _f:
            return pickle.dump(data, _f, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def model_walker(bdir, fmt='list'):
        models_files = []
        if fmt == 'list':
            ### Easy formating
            for root, dirnames, filenames in os.walk(bdir):
                for filename in fnmatch.filter(filenames, '*.pk'):
                    models_files.append(os.path.join(root, filename))
            return models_files
        else:
            ### More Complex formating
            tree = { 'json': [],
                    'pk': [],
                    'inference': [] }
            for filename in fnmatch.filter(filenames, '*.pk'):
                if filename.startswith(('dico.','vocab.')):
                    dico_files.append(os.path.join(root, filename))
                else:
                    corpus_files.append(os.path.join(root, filename))
            raise NotImplementedError()
        return tree


    @staticmethod
    def get_cls_name(cls):
        clss = str(cls).split()[1]
        return clss.split('.')[-1].replace("'>", '')


    def expe_init(self, expe, _seed_path='/tmp/pymake.seed'):
        _seed = expe.get('seed')

        if _seed is None:
            seed = np.random.randint(0, 2**32)
        elif type(_seed) is int:
            seed = _seed
        elif _seed is True:
            seed = None
            try:
                np.random.set_state(self.load(_seed_path))
            except FileNotFoundError as e:
                lgg.error("Cannot initialize seed, %s file does not exist." % _seed_path)
                self.save(np.random.get_state(), _seed_path, silent=True)
                raise FileNotFoundError('%s file just created, try again !')

        if seed:
            # if no seed is given, it impossible ti get a seed from numpy
            # https://stackoverflow.com/questions/32172054/how-can-i-retrieve-the-current-seed-of-numpys-random-number-generator
            np.random.seed(seed)

        # Init I/O settings
        expe['_output_path'] = self.make_output_path(expe)
        expe['_input_path'] = self.make_input_path(expe)

        self.save(np.random.get_state(), _seed_path, silent=True)
        self._seed = seed
        return seed


    def execute(self, indexs=None):
        ''' Execute Exp Sequentially '''

        if not indexs:
            indexs = range(len(self))

        self.lod = [self.lod[i] for i in indexs]
        self.exp_tensor = self.make_tensor(self.lod)

        if 'script' in self._conf:
            script = self._conf.pop('script')
            self.remove('script')
            self.remove('_do')
        else:
            lgg.error('==> Error : Who need to specify a script. (--script)')
            exit(10)

        _script, script_args = Script.get(script[0], script[1:])

        # Raw search
        #script_name = script[0]
        #script_args = script[1:]
        #Scripts = mloader.ScriptsLoader.get_packages()
        #if not script_name in Scripts:
        #    method_by_cls = mloader.ScriptsLoader.lookup_methods()
        #    if script_name in sum(method_by_cls.values(), []):
        #        # check if it is a method reference
        #        script_args = [script_name] + script_args
        #        script_name = next(k.lower() for (k,v) in method_by_cls.items() if script_name in v)
        #    else:
        #        raise ValueError('error: Unknown script: %s' % (script_name))

        if script_args:
            self.update(_do=script_args)
        #self.pymake(sandbox=Scripts[script_name])
        self.pymake(sandbox=_script)

    def execute_parallel(self, indexs=None):
        cmdlines = []
        basecmd = sys.argv.copy()
        basecmd = ['python3', './zymake.py'] + basecmd[1:]
        #basecmd = ['pymake'] + basecmd[1:] # PATH and PYTHONPATH varible missing to be able to execute "pymake"

        if not indexs:
            indexs = range(len(self))
        else:
            [basecmd.remove(str(i)) for i in indexs]

        basecmd = ' '.join(basecmd)

        for index in indexs:
            cmdlines.append( basecmd.replace('runpara', 'run %s'%index, 1) )

        net = self._conf.get('_net', False)
        if net:
            NDL = get_global_settings('loginfile')
            PWD = get_global_settings('remote_pwd')
            cmd = ['parallel', '-u', '-C', "' '", '--eta', '--progress',
                   '--sshloginfile', NDL, '--workdir', PWD, '--env', 'OMP_NUM_THREADS',  ':::', '%s'%('\n'.join(cmdlines))]
        else:
            n_cores = str(self._conf.get('_cores', 0))
            cmd = ['parallel', '-j', n_cores, '-u', '-C', "' '", '--eta', '--progress', ':::', '%s'%('\n'.join(cmdlines))]

        #stdout = subprocess.check_output(cmd)
        #print(stdout.decode())
        for line in self.subexecute(cmd):
            print(line, end='')

    @staticmethod
    def subexecute(cmd):
        popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)
        for stdout_line in iter(popen.stdout.readline, ""):
            yield stdout_line
        popen.stdout.close()
        return_code = popen.wait()
        if return_code:
            raise subprocess.CalledProcessError(return_code, cmd)

    def notebook(self):
        from nbformat import v4 as nbf
        nb = nbf.new_notebook()
        text = ''
        code = ''
        nb['cells'] = [nbf.new_markdown_cell(text),
                       nbf.new_code_cell(code) ]
        return

    def init_folders(self):
        from string import Template
        from os.path import join
        from pymake.util.utils import set_global_settings

        pwd = os.getenv('PWD')
        if os.path.isfile(join(pwd, 'pymake.cfg')):
            print('pymake.cfg file already exists.')
            exit(11)


        cwd = os.path.dirname(__file__)
        folders = ['spec', 'script', 'model']
        open(join(pwd, '__init__.py'), 'a').close()
        spec = {'projectname':os.path.basename(pwd)}
        settings = {}
        for d in folders:
            os.makedirs(d, exist_ok=True)
            with open(join(cwd, '%s.template'%(d))) as _f:
                template = Template(_f.read())

            open(join(pwd, d,  '__init__.py'), 'a').close()
            with open(join(pwd, d,  'template_%s.py'%(d)), 'a') as _f:
                _f.write(template.substitute(spec))

            if d in ['spec', 'script']:
                settings.update({'default_%s'%(d):'.'.join((spec['projectname'], d))})
            else: # share model
                settings.update({'contrib_%s'%(d):'.'.join((spec['projectname'], d))})

        settings.update(project_data='data')
        set_global_settings(settings)
        print('update project: {projectname}'.format(**spec))
        return self.update_index()

    def pushcmd2hist(self):
        from pymake.util.utils import tail
        bdir = self.data_path
        fn = os.path.join(bdir, '.pymake_hist')
        if not os.path.isfile(fn):
            open(fn, 'a').close()
            return

        cmd = sys.argv.copy()
        cmd[0] = os.path.basename(cmd[0])
        cmd = ' '.join(cmd)
        _tail = tail(fn, 10)

        with open(fn, 'a') as _f:
            if not cmd in _tail:
                return _f.write(cmd+'\n')


    def show_history(self):
        from pymake.util.utils import tail
        n_lines = int(self._conf.get('N', 20))
        bdir = self.data_path
        fn = os.path.join(bdir, '.pymake_hist')
        if not os.path.isfile(fn):
            lgg.error('hist file does not exist.')
            return

        _tail = tail(fn, n_lines)

        print('\n'.join(_tail))


    def update_index(self):
        from pymake.index.indexmanager import IndexManager as IX
        IX.build_indexes()

    def pymake(self, sandbox=ExpeFormat):
        ''' Walk Trough experiments. '''

        if 'do_list' in self.exp_tensor:
            print('Available methods for %s: ' % (sandbox))
            print(*self.functable(sandbox) , sep='\n')
            exit()


        sandbox._preprocess_(self)
        if self._conf.get('simulate'):
            self.simulate()

        for id_expe, expe in enumerate(self.lod):
            _expe = ExpSpace(**expe)

            pt = dict((key, value.index(_expe[key])) for key, value in self.exp_tensor.items() if (isinstance(_expe[key], (basestring, int, float)) and key not in self._reserved_keywords))
            pt['expe'] = id_expe

            # Init Expe
            self.expe_init(_expe)
            try:
                expbox = sandbox(pt, _expe, self)
            except FileNotFoundError as e:
                lgg.error('ignoring %s'%e)
                continue
            except Exception as e:
                print(('Error during '+colored('%s', 'red')+' Initialization.') % (str(sandbox)))
                traceback.print_exc()
                exit(2)

            # Expe Preprocess
            expbox._preprocess()

            # Setup handler
            if hasattr(_expe, '_do') and len(_expe._do) > 0:
                # ExpFormat task ? decorator and autoamtic argument passing ....
                do = _expe._do
                pmk = getattr(expbox, do[0])
            else:
                do = ['__call__']
                pmk = expbox

            # Launch handler
            args = do[1:]
            try:
                pmk(*args)
            except KeyboardInterrupt:
                # it's hard to detach matplotlib...
                break
            except Exception as e:
                print(('Error during '+colored('%s', 'red')+' Expe.') % (do))
                traceback.print_exc()
                exit(2)

            # Expe Postprocess
            expbox._postprocess()

        return sandbox._postprocess_(self)

    @property
    def data_path(self):
        return get_global_settings('project_data')

