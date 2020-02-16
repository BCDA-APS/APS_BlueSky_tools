
"""
execute a sequence of bluesky plans from a file

.. autosummary::
   
   ~CommandFileReadError
   ~get_command_list
   ~parse_Excel_command_file
   ~parse_text_command_file
   ~register_command_handler
   ~run_command_file
   ~summarize_command_file
"""

__all__ = """
    CommandFileReadError
    get_command_list
    parse_Excel_command_file
    parse_text_command_file
    register_command_handler
    run_command_file
    summarize_command_file
""".split()

import logging
logger = logging.getLogger(__name__)

from bluesky import plan_stubs as bps
import os
from ..utils import command_list_as_table
from ..utils import ExcelReadError
from ..utils import ExcelDatabaseFileGeneric
from ..utils import split_quoted_line


# internal use, allows redefinition of execute_command_list()
_COMMAND_HANDLER_ = execute_command_list


class CommandFileReadError(IOError): ...


def execute_command_list(filename, commands, md={}):
    """
    plan: execute the command list

    The command list is a tuple described below.

    * Only recognized commands will be executed.
    * Unrecognized commands will be reported as comments.
    
    See example implementation with APS USAXS instrument:
    https://github.com/APS-USAXS/ipython-usaxs/blob/5db882c47d935c593968f1e2144d35bec7d0181e/profile_bluesky/startup/50-plans.py#L381-L469

    PARAMETERS

    filename : str
        Name of input text file.  Can be relative or absolute path,
        such as "actions.txt", "../sample.txt", or
        "/path/to/overnight.txt".
    commands : list[command]
        List of command tuples for use in ``execute_command_list()``

    where

    command : tuple
        (action, OrderedDict, line_number, raw_command)
    action: str
        names a known action to be handled
    parameters: list
        List of parameters for the action.
        The list is empty of there are no values
    line_number: int
        line number (1-based) from the input text file
    raw_command: obj (str or list(str)
        contents from input file, such as:
        ``SAXS 0 0 0 blank``

    SEE ALSO

    .. autosummary::
    
        ~execute_command_list
        ~register_command_handler
        ~run_command_file
        ~summarize_command_file
        ~parse_Excel_command_file
        ~parse_text_command_file

    *new in apstools release 1.1.7*
    """
    full_filename = os.path.abspath(filename)

    if len(commands) == 0:
        yield from bps.null()
        return

    print(f"Command file: {filename}")
    print(command_list_as_table(commands))

    for command in commands:
        action, args, i, raw_command = command
        print(f"file line {i}: {raw_command}")

        _md = {}
        _md["full_filename"] = full_filename
        _md["filename"] = filename
        _md["line_number"] = i
        _md["action"] = action
        _md["parameters"] = args    # args is shorter than parameters, means the same thing here

        _md.update(md or {})      # overlay with user-supplied metadata

        action = action.lower()
        if action == "tune_optics":
            # example: yield from tune_optics(md=_md)
            logger.warn(
                (
                    f"This is an example.  action={raw_command}."
                    "  Must define your own execute_command_list() function"
                )
            )
            yield from bps.null()

        else:
            print(f"no handling for line {i}: {raw_command}")


def get_command_list(filename):
    """
    return command list from either text or Excel file

    SEE ALSO

    .. autosummary::
    
        ~execute_command_list
        ~get_command_list
        ~register_command_handler
        ~run_command_file
        ~summarize_command_file
        ~parse_Excel_command_file
        ~parse_text_command_file

    *new in apstools release 1.1.7*
    """
    full_filename = os.path.abspath(filename)
    if not os.path.exists(full_filename):
        raise IOError(f"file not found: {filename}")
    try:
        commands = parse_Excel_command_file(filename)
    except ExcelReadError:
        try:
            commands = parse_text_command_file(filename)
        except ValueError as exc:
            raise CommandFileReadError(
                f"could not read {filename} as command list file: {exc}"
            )
    return commands


def parse_Excel_command_file(filename):
    """
    parse an Excel spreadsheet with commands, return as command list

    TEXT view of spreadsheet (Excel file line numbers shown)::

        [1] List of sample scans to be run
        [2]
        [3]
        [4] scan    sx  sy  thickness   sample name
        [5] FlyScan 0   0   0   blank
        [6] FlyScan 5   2   0   blank

    PARAMETERS

    filename : str
        Name of input Excel spreadsheet file.  Can be relative or absolute path,
        such as "actions.xslx", "../sample.xslx", or
        "/path/to/overnight.xslx".

    RETURNS

    list of commands : list[command]
        List of command tuples for use in ``execute_command_list()``

    RAISES

    FileNotFoundError
        if file cannot be found

    SEE ALSO

    .. autosummary::
    
        ~get_command_list
        ~register_command_handler
        ~run_command_file
        ~summarize_command_file
        ~parse_text_command_file

    *new in apstools release 1.1.7*
    """
    full_filename = os.path.abspath(filename)
    assert os.path.exists(full_filename)
    xl = ExcelDatabaseFileGeneric(full_filename)

    commands = []

    if len(xl.db) > 0:
        for i, row in enumerate(xl.db.values()):
            action, *values = list(row.values())

            # trim off any None values from end
            while len(values) > 0:
                if values[-1] is not None:
                    break
                values = values[:-1]

            commands.append((action, values, i+1, list(row.values())))

    return commands


def parse_text_command_file(filename):
    """
    parse a text file with commands, return as command list

    * The text file is interpreted line-by-line.
    * Blank lines are ignored.
    * A pound sign (#) marks the rest of that line as a comment.
    * All remaining lines are interpreted as commands with arguments.

    Example of text file (no line numbers shown)::

        #List of sample scans to be run
        # pound sign starts a comment (through end of line)

        # action  value
        mono_shutter open

        # action  x y width height
        uslits 0 0 0.4 1.2

        # action  sx  sy  thickness   sample name
        FlyScan 0   0   0   blank
        FlyScan 5   2   0   "empty container"

        # action  sx  sy  thickness   sample name
        SAXS 0 0 0 blank

        # action  value
        mono_shutter close

    PARAMETERS

    filename : str
        Name of input text file.  Can be relative or absolute path,
        such as "actions.txt", "../sample.txt", or
        "/path/to/overnight.txt".

    RETURNS

    list of commands : list[command]
        List of command tuples for use in ``execute_command_list()``

    RAISES

    FileNotFoundError
        if file cannot be found

    SEE ALSO

    .. autosummary::
    
        ~execute_command_list
        ~get_command_list
        ~register_command_handler
        ~run_command_file
        ~summarize_command_file
        ~parse_Excel_command_file

    *new in apstools release 1.1.7*
    """
    full_filename = os.path.abspath(filename)
    assert os.path.exists(full_filename)
    with open(full_filename, "r") as fp:
        buf = fp.readlines()

    commands = []
    for i, raw_command in enumerate(buf):
        row = raw_command.strip()
        if row == "" or row.startswith("#"):
            continue                    # comment or blank

        else:                           # command line
            action, *values = split_quoted_line(row)
            commands.append((action, values, i+1, raw_command.rstrip()))

    return commands


def register_command_handler(handler=None):
    """
    (re)define the function called to execute the command list

    PARAMETERS

    handler : obj
        Reference of the ``execute_command_list`` function
        to be used from :func:`~apstools.plans.run_command_file()`.
        If ``None`` or not provided, 
        will reset to :func:`~apstools.plans.execute_command_list()`,
        which is also the initial setting.

    SEE ALSO

    .. autosummary::
    
        ~execute_command_list
        ~get_command_list
        ~register_command_handler
        ~summarize_command_file
        ~parse_Excel_command_file
        ~parse_text_command_file

    *new in apstools release 1.1.7*
    """
    global _COMMAND_HANDLER_
    _COMMAND_HANDLER_ = handler or execute_command_list


def run_command_file(filename, md={}):
    """
    plan: execute a list of commands from a text or Excel file

    * Parse the file into a command list
    * yield the command list to the RunEngine (or other)

    SEE ALSO

    .. autosummary::
    
        ~execute_command_list
        ~get_command_list
        ~register_command_handler
        ~summarize_command_file
        ~parse_Excel_command_file
        ~parse_text_command_file

    *new in apstools release 1.1.7*
    """
    commands = get_command_list(filename)
    yield from _COMMAND_HANDLER_(filename, commands)


def summarize_command_file(filename):
    """
    print the command list from a text or Excel file

    SEE ALSO

    .. autosummary::
    
        ~execute_command_list
        ~get_command_list
        ~run_command_file
        ~parse_Excel_command_file
        ~parse_text_command_file

    *new in apstools release 1.1.7*
    """
    commands = get_command_list(filename)
    print(f"Command file: {filename}")
    print(command_list_as_table(commands))
