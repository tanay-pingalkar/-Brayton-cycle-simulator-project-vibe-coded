"""Figures, display tables and JSON/Markdown reports (REQ-R01).

``CyclePlotter`` is imported lazily, so text-only users (CLI without --plots)
do not pay matplotlib's import cost.
"""

from brayton_cycle.reporting.citations import property_citation
from brayton_cycle.reporting.report import ReportGenerator
from brayton_cycle.reporting.tables import (STATION_HEADERS, input_rows, kpi_rows, optimum_rows,
                                            station_rows)


def __getattr__(name: str):  # PEP 562 lazy import
    if name == "CyclePlotter":
        from brayton_cycle.reporting.plots import CyclePlotter

        return CyclePlotter
    raise AttributeError(name)


__all__ = ["STATION_HEADERS", "CyclePlotter", "ReportGenerator", "input_rows", "kpi_rows", "optimum_rows",
           "property_citation", "station_rows"]
