"""
A manager for the plugins

  From Pro Python System Administration by Rytis Sileika
"""

import sys
import os
import logging

logger = logging.getLogger('spectrum_logger')


class Plugin(object):
    pass


class PluginManager:
    # Discovery and registration
    def __init__(self, path=None, plugin_init_arguments={}, register=True):
        if path:
            self._plugin_dir = path
        else:
            self._plugin_dir = os.path.dirname(__file__) + "/../plugins"
        self._help_strings = {}
        self._plugins = {}
        self._load_plugins()
        if register:
            self._register_plugins(**plugin_init_arguments)

    def get_plugin_helps(self) -> {}:
        return self._help_strings

    def _load_plugins(self):
        """
        Load the modules to get the help strings, but don't register the modules
        :return:
        """
        sys.path.append(self._plugin_dir)
        plugin_files = [fn for fn in os.listdir(self._plugin_dir) if fn.startswith('plugin_') and fn.endswith('.py')]
        plugin_modules = [m.split('.')[0] for m in plugin_files]
        for module in plugin_modules:
            mod = __import__(module)
            self._help_strings[module] = mod.help_string

    def _register_plugins(self, **kwargs):
        for plugin in Plugin.__subclasses__():
            obj = plugin(**kwargs)
            self._plugins[obj] = obj._methods if hasattr(obj, '_methods') else []
            self._help_strings[obj.__module__] = obj.help()

        info = f"Registered valid plugins: "
        for plugin in self._plugins:
            info += f"{plugin.__module__}, "
        logger.info(info)

    def call_plugin_method(self, method, args={}, methods=[]):
        results = {}  # a dictionary of things to pass back
        for plugin in self._plugins:
            if not methods or (set(methods) & set(self._plugins[plugin])):
                try:
                    # lookup and execute the required plugin object/method
                    result = (getattr(plugin, method)(**args))
                    # add to the returned dictionary the output from this plugin, with it's preferred result key
                    if result is not None:
                        name, value = result
                        results[name] = value
                except AttributeError:
                    pass
        return results
