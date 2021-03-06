import sys, traceback
from django.conf import settings
from django.utils.importlib import import_module
from django.core.exceptions import ImproperlyConfigured

def debug(func):
    # @debug is handy when debugging distutils requests
    if settings.DEBUG:
        def _wrapped(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except:
                traceback.print_exception(*sys.exc_info())
        return _wrapped
    else:
        return func

def get_class(import_path):
    try:
        dot = import_path.rindex('.')
    except ValueError:
        raise ImproperlyConfigured("'%s' isn't a valid python path." % import_path)
    module, classname = import_path[:dot], import_path[dot+1:]
    try:
        mod = import_module(module)
    except ImportError, e:
        raise ImproperlyConfigured('Error importing module %s: "%s"' % (module, e))
    try:
        return getattr(mod, classname)
    except AttributeError:
        raise ImproperlyConfigured('Module "%s" does not define "%s"' % (module, classname))
