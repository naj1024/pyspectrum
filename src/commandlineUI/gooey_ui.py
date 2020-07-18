#########
#
# Import a simple commandlineUI creator that works on argparse values. If we can't import then
# create the decorator so that it can be ignored and left in place - just before main()
#
# If gooey is not available we will still work ok, and you can turn off the commandlineUI
# on systems that have it installed by using the --ignore-gooey option
#
####
import logging

logger = logging.getLogger('spectrum_logger')

try:
    from gooey import Gooey
    logger.info("Found gooey support in environment")
except ImportError:
    logger.info("No gooey support in environment")
    # make the lack of Gooey transparent
    from functools import wraps

    # took a while to google this, modified from code at:
    # https://realpython.com/primer-on-python-decorators/#both-please-but-never-mind-the-bread
    def Gooey(_func=None, **kwargs_1):
        def decorator_func(func):
            @wraps(func)
            def wrapper_func(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper_func

        if _func is None:
            return decorator_func
        else:
            return decorator_func(_func)
