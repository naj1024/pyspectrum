import importlib
import logging
import os
import sys

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')


class DataSourceFactory:
    """
    Create a DataSource object when requested
    """

    def __init__(self):
        """
        Find and load all the data sources we can support in the current environment

        Import all the data sources we can find - DO NOT initialise or create them though.
        This is a type of plugin, but we don't make the 'things' until we are told to create() one
        As we only want to support one type of input at a time it doesn't make sense to create
        things we don't need.
        """

        self._data_sources = {}  # dictionary of names to actual things we support
        self._data_helps = {}  # the help strings for each name
        self._data_web_helps = {}  # the web help strings for each name

        # add the current directory to the search path
        self._input_source_dir = os.path.dirname(__file__)
        sys.path.append(self._input_source_dir)
        # find all the files that have the pattern DataSource_*.py
        input_source_files = [fn for fn in os.listdir(self._input_source_dir) if
                              fn.startswith('DataSource_') and fn.endswith('.py')]
        # Drop the .py to get the module names
        input_source_modules = [m.split('.')[0] for m in input_source_files]

        # print("Importing input_source_modules", input_source_modules)
        for input_source_module in input_source_modules:
            # print(f"Importing data source: {input_source_module}")
            module = importlib.import_module(input_source_module)
            # Check it imported OK
            name, err_str = getattr(module, "is_available")()
            if err_str == "":
                # add it to the types we support
                self._data_sources[name] = getattr(module, "Input")
                self._data_helps[name] = getattr(module, "help_string")
                self._data_web_helps[name] = getattr(module, "web_help_string")

    def sources(self) -> [str]:
        """
        Return a list of names of source that we have registered for creation
        :return: A list of names as strings
        """
        return list(self._data_sources.keys())

    def help_strings(self) -> {str: str}:
        """
        Return a list of help strings from the the supported input sources
        :return: A dictionary of help strings for the input sources
        """
        return self._data_helps

    def web_help_strings(self) -> {str: str}:
        """
        Return a list of web help strings from the the supported input sources
        :return: A dictionary of help strings for the input sources
        """
        return self._data_web_helps

    def create(self,
               input_type: str,
               parameters: str,
               data_type: str,
               sample_rate: float,
               centre_frequency: float,
               input_bw: float
               ) -> DataSource:
        """
        Create a new data source

        :param input_type: One of the supported input types
        :param parameters: The underlying thing that the new type requires to work, e.g. filename or ip address
        :param data_type: The data type the source understands, the data will be converted by the source
        :param sample_rate: The sample rate this source is producing at, can be overridden
        :param centre_frequency: The frequency the source is tuned to
        :param input_bw: The filtered input bw of the source
        :return: The object
        """
        creator = self._data_sources.get(input_type)
        if not creator:
            msg = f"Data source type '{input_type}' not supported."
            logger.error(msg)
            raise ValueError(msg)

        source = creator(parameters,
                         data_type,
                         sample_rate,
                         centre_frequency,
                         input_bw)

        return source
