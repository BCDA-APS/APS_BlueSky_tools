#!/usr/bin/env python

"""
record a snapshot of some PVs using Bluesky, ophyd, and databroker

USAGE::

    (base) user@hostname .../pwd $ bluesky_snapshot -h
    usage: bluesky_snapshot [-h] [-b BROKER_CONFIG] [-m METADATA_SPEC] [-r] [-v]
                            EPICS_PV [EPICS_PV ...]

    record a snapshot of some PVs using Bluesky, ophyd, and databroker
    version=0.0.40+26.g323cd35

    positional arguments:
      EPICS_PV              EPICS PV name

    optional arguments:
      -h, --help            show this help message and exit
      -b BROKER_CONFIG      YAML configuration for databroker, default:
                            mongodb_config
      -m METADATA_SPEC, --metadata METADATA_SPEC
                            additional metadata, enclose in quotes, such as -m
                            "purpose=just tuned, situation=routine"
      -r, --report          suppress snapshot report
      -v, --version         show program's version number and exit

"""

# -----------------------------------------------------------------------------
# :author:    Pete R. Jemian
# :email:     jemian@anl.gov
# :copyright: (c) 2017-2021, UChicago Argonne, LLC
#
# Distributed under the terms of the Creative Commons Attribution 4.0 International Public License.
#
# The full license is in the file LICENSE.txt, distributed with this software.
# -----------------------------------------------------------------------------


import argparse
from collections import OrderedDict
from io import StringIO
import sys
import time
import tkinter as tk
import tkinter.ttk as ttk

from databroker import Broker

from . import utils as APS_utils
from . import plans as APS_plans
from . import callbacks as APS_callbacks
from . import textreadonly


BROKER_CONFIG = "mongodb_config"


def get_args():
    """
    get command line arguments
    """
    from .__init__ import __version__

    doc = __doc__.strip().splitlines()[0].strip()
    doc += f" version={__version__}"

    parser = argparse.ArgumentParser(description=doc)

    parser.add_argument(
        "EPICS_PV",
        action="store",
        nargs="+",
        help="EPICS PV name",
        default="",
    )

    # optional arguments
    text = "YAML configuration for databroker"
    text += f", default: {BROKER_CONFIG}"
    parser.add_argument(
        "-b",
        action="store",
        dest="broker_config",
        help=text,
        default=BROKER_CONFIG,
    )

    text = """
    additional metadata, enclose in quotes,
    such as -m "purpose=just tuned, situation=routine"
    """
    parser.add_argument(
        "-m",
        "--metadata",
        action="store",
        dest="metadata_spec",
        help=text,
        default="",
    )

    parser.add_argument(
        "-r",
        "--report",
        action="store_false",
        dest="report",
        help="suppress snapshot report",
        default=True,
    )

    parser.add_argument(
        "-v", "--version", action="version", version=__version__
    )

    return parser.parse_args()


def parse_metadata(args):
    md = OrderedDict()
    if len(args.metadata_spec.strip()) > 0:
        for metadata in args.metadata_spec.split(","):
            parts = metadata.strip().split("=")
            if len(parts) == 2:
                md[parts[0].strip()] = parts[1].strip()
            else:
                msg = f"incorrect metadata specification {metadata}"
                msg += ", must specify key = value [, key2 = value2 ]"
                raise ValueError(msg)
    return md


def snapshot_cli():
    """
    given a list of PVs on the command line, snapshot and print report

    EXAMPLES::

        snapshot.py pv1 [more pvs ...]
        snapshot.py `cat pvlist.txt`

    Note that these are equivalent::

        snapshot.py rpi5bf5:0:humidity rpi5bf5:0:temperature
        snapshot.py rpi5bf5:0:{humidity,temperature}

    """
    from bluesky import RunEngine

    args = get_args()

    md = OrderedDict(purpose="archive a set of EPICS PVs")
    md.update(parse_metadata(args))

    obj_dict = APS_utils.connect_pvlist(args.EPICS_PV, wait=False)
    time.sleep(2)  # FIXME: allow time to connect

    db = Broker.named(args.broker_config)
    RE = RunEngine({}, scan_id_source=None)
    RE.subscribe(db.insert)

    uuid_list = RE(APS_plans.snapshot(obj_dict.values(), md=md))

    if args.report:
        snap = list(db(uuid_list[0]))[0]
        APS_callbacks.SnapshotReport().print_report(snap)


class Capturing(list):  # LGTM
    """
    capture stdout output from a Python function call

    https://stackoverflow.com/a/16571630/1046449
    """

    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._stringio = StringIO()
        return self

    def __exit__(self, *args):
        self.extend(self._stringio.getvalue().splitlines())
        del self._stringio  # free up some memory
        sys.stdout = self._stdout


def snapshot_gui(config=None):
    """run the snapshot viewer"""
    SnapshotGui(config or BROKER_CONFIG)


class SnapshotGui(object):
    """
    Browse and display snapshots in a Tkinter GUI

    USAGE (from command line)::

        bluesky_snapshot_viewer

    """

    search_criteria = dict(plan_name="snapshot")

    def __init__(self, config=None):
        config = config or BROKER_CONFIG
        self.db = Broker.named(config)
        self.uids = []

        self._build_gui_()
        self.tree.bind("<<TreeviewSelect>>", self.receiver)
        self.load_data()
        tk.mainloop()

    def _build_gui_(self):
        self.main_window = tk.Tk()
        self.main_window.winfo_toplevel().title("Bluesky snapshot viewer")

        m = tk.PanedWindow(self.main_window, orient=tk.HORIZONTAL)
        m.pack(fill=tk.BOTH, expand=True)

        lpane = tk.Label(m, text="left pane")
        m.add(lpane)

        rpane = tk.Label(m, text="right pane")
        m.add(rpane)

        # -- left pane, tree of available snapshots

        fr = ttk.Frame(lpane)
        fr.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        xsb = ttk.Scrollbar(fr, orient=tk.HORIZONTAL)
        ysb = ttk.Scrollbar(fr, orient=tk.VERTICAL)
        xsb.pack(side=tk.BOTTOM, fill=tk.X)
        ysb.pack(side=tk.RIGHT, fill=tk.Y)

        column_keys = []
        column_keys.append("iso8601")
        self.tree = ttk.Treeview(fr, columns=column_keys)
        self.tree["xscroll"] = xsb.set
        self.tree["yscroll"] = ysb.set

        self.tree.column("#0", width=90, stretch=tk.NO)
        self.tree.column("iso8601", width=70, stretch=tk.NO)
        self.tree.heading("#0", text="date")
        self.tree.heading("iso8601", text="time")

        xsb.configure(command=self.tree.xview)
        ysb.configure(command=self.tree.yview)
        self.tree.configure(xscrollcommand=xsb.set, yscrollcommand=ysb.set)
        self.tree.pack(fill=tk.Y, expand=True)

        self.refresh_button = ttk.Button(
            lpane, text="refresh list", command=self.refresh
        )
        self.refresh_button.pack(fill=tk.X)

        # -- right pane, content of selected snapshot

        fr = ttk.Frame(rpane)
        fr.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        xsb = ttk.Scrollbar(fr, orient=tk.HORIZONTAL)
        ysb = ttk.Scrollbar(fr, orient=tk.VERTICAL)
        xsb.pack(side=tk.BOTTOM, fill=tk.X)
        ysb.pack(side=tk.RIGHT, fill=tk.Y)

        self.snapview = textreadonly.TextReadOnly(fr)
        xsb.configure(command=self.snapview.xview)
        ysb.configure(command=self.snapview.yview)
        self.snapview.configure(
            xscrollcommand=xsb.set, yscrollcommand=ysb.set
        )
        self.snapview.pack(expand=True, fill=tk.BOTH)

    @property
    def get_snapshots(self):
        return self.db(**self.search_criteria)

    def receiver(self, event):
        from . import callbacks

        item_index = event.widget.focus()
        if item_index in self.uids:
            hh = self.db(plan_name="snapshot", uid=item_index)
            header = list(hh)[0]
            with Capturing() as lines:
                callbacks.SnapshotReport().print_report(header)
            self.show_contents("\n".join(lines))

    def show_contents(self, text):
        self.snapview.delete("1.0", tk.END)
        self.snapview.insert(tk.END, text)

    def refresh(self):
        kids = self.tree.get_children()
        for item in kids:
            self.tree.delete(item)
        self.uids = []
        self.load_data()

    def load_data(self):
        parents = []
        for h in self.get_snapshots:
            start_doc = h.start
            uid = start_doc["uid"]
            iso = start_doc["iso8601"].split(".")[0]
            ymd, hms = iso.split()
            if ymd not in parents:
                parents.append(ymd)
                self.tree.insert("", "end", ymd, text=ymd)
            self.uids.append(uid)
            self.tree.insert(ymd, "end", iid=uid, values=[hms])


if __name__ == "__main__":
    snapshot_cli()
