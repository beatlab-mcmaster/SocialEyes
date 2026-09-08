
from ..monitoring.device import DeviceState
from .table_presenter import DeviceTablePresenter
from .table_view import Column, DeviceTableView
from .widgets import SelectableRowsDataTable


class DeviceTableController:
    def __init__(
              self,
              table_widget: SelectableRowsDataTable,
              ip_addrs: list[str],
              column_layout: list[Column]
    ):
        self._view = DeviceTableView(table_widget, ip_addrs, column_layout)
        self._presenter = DeviceTablePresenter()
        self._column_layout = column_layout

    def time_ago_threshold(self, threshold_seconds: float, ip_addrs: list[str] | None = None) -> None:
        self._presenter.time_ago_threshold(threshold_seconds, ip_addrs)

    def selected_ip_addrs(self) -> list[str]:
            return self._view.selected_ip_addrs()

    def update_table(self, states: dict[str, DeviceState]) -> None:
        for ip_addr, field, val in self._presenter.diff_updates(states):
            self._view.update_cell(ip_addr, field, val)
