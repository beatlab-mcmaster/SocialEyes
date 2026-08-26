import logging
from dataclasses import dataclass
from typing import Any

from textual.widgets._data_table import ColumnKey, RowKey

from .device_state import DeviceStateField
from .widgets import SelectableRowsDataTable


@dataclass
class Column:
    name: str
    field: DeviceStateField | None

class DeviceTableView:

    _logger: logging.Logger

    _table: SelectableRowsDataTable
    _column_keys: list[ColumnKey]
    _row_keys: list[RowKey]
    _field_to_column_key: dict[DeviceStateField, ColumnKey]
    _ip_to_row_key: dict[str, RowKey]
    _ip_addr_col_index: int
    
    def __init__(self, table: SelectableRowsDataTable, ip_addrs: list[str], column_layout: list[Column]):
        # Init columns
        self._column_keys = table.add_columns(*[col.name for col in column_layout])

        fields = [col.field for col in column_layout]
        self._ip_addr_col_index = fields.index(DeviceStateField.IP) - 1

        # Init rows with IP addresses and empty values for other columns
        data = [
            tuple(ip if field is DeviceStateField.IP else None for field in fields[1:])
            for ip in ip_addrs
        ]
        self._row_keys = table.add_rows(data)

        # Create mappings for quick access to rows and columns based on IP addresses and fields
        self._field_to_column_key = {
            field: self._column_keys[i] for i, field in enumerate(fields) if field is not None
        }
        self._ip_to_row_key = dict(zip(ip_addrs, self._row_keys))

        self._table = table
        self._logger = logging.getLogger(__name__)

    def selected_ip_addrs(self) -> list[str]:
        return [row.data[self._ip_addr_col_index] for row in self._table.selected_rows]

    def update_cell(self, ip_addr: str, field: DeviceStateField, value: Any) -> None:
        row_key = self._ip_to_row_key.get(ip_addr)
        column_key = self._field_to_column_key.get(field)
        if row_key is None or column_key is None:
            return
        self._table.update_cell(row_key, column_key, value, update_width=True)