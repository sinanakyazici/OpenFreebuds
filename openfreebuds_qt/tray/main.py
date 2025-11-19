import asyncio
from typing import Optional

from PIL import ImageQt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon
from qasync import asyncSlot

from openfreebuds import IOpenFreebuds, OfbEventKind
from openfreebuds.exceptions import OfbServerDeadError
from openfreebuds.utils.logger import create_logger
from openfreebuds_qt.config.main import OfbQtConfigParser
from openfreebuds_qt.generic import IOfbQtApplication
from openfreebuds_qt.generic import IOfbTrayIcon
from openfreebuds_qt.tray.menu import OfbQtTrayMenu
from openfreebuds_qt.utils import OfbCoreEvent, qt_error_handler, create_tray_icon
from openfreebuds_qt.utils.icon.tray_factory import create_battery_percentage_icon

log = create_logger("OfbTrayIcon")


class OfbTrayIcon(IOfbTrayIcon):
    """
    OpenFreebuds Tray icon implementation
    """

    def __init__(self, context: IOfbQtApplication):
        super().__init__(None)

        self._last_tooltip = ""

        # noinspection PyUnresolvedReferences
        self.activated.connect(self._on_click)

        self.ctx = context
        self.ofb = context.ofb
        self.config = OfbQtConfigParser.get_instance()

        self.ui_update_task: Optional[asyncio.Task] = None

        self.menu = OfbQtTrayMenu(self, self.ctx, self.ofb)
        self.setContextMenu(self.menu)

        # Battery percentage tray icons
        self.battery_left_icon: Optional[QSystemTrayIcon] = None
        self.battery_right_icon: Optional[QSystemTrayIcon] = None
        self.battery_case_icon: Optional[QSystemTrayIcon] = None

    @asyncSlot(QSystemTrayIcon.ActivationReason)
    async def _on_click(self, reason):
        if (
            reason == self.ActivationReason.Trigger
            and await self.ofb.get_state() == self.ofb.STATE_CONNECTED
        ):
            async with qt_error_handler("OfbTrayIcon_OnClick", self.ctx):
                tray_shortcut = self.config.get("ui", "tray_shortcut", "next_mode")
                await self.ofb.run_shortcut(tray_shortcut)

    async def boot(self):
        """
        Will start UI update loop and perform other preparations on boot
        """
        async with qt_error_handler("OfbTrayIcon_Boot", self.ctx):
            if self.ui_update_task is None:
                self.ui_update_task = asyncio.create_task(self._update_loop())

            await self._update_ui(OfbCoreEvent(None))

    async def close(self):
        """
        Will stop UI update loop
        """
        if self.ui_update_task is not None:
            self.ui_update_task.cancel()
            await self.ui_update_task
            self.ui_update_task = None

    async def _update_ui(self, event: OfbCoreEvent):
        """
        UI update callback
        """

        state = await self.ofb.get_state()

        # Update icon
        icon = create_tray_icon(self.config.get_tray_icon_theme(),
                                state,
                                await self.ofb.get_property("battery", "global", 0),
                                await self.ofb.get_property("anc", "mode", "normal"))
        pixmap = QIcon(ImageQt.toqpixmap(icon))
        self.setIcon(pixmap)

        # Update menu and tooltip
        if state == IOpenFreebuds.STATE_CONNECTED:
            self.setToolTip(await self._get_tooltip_text(event))
        elif state == IOpenFreebuds.STATE_WAIT:
            self.setToolTip(self.tr("OpenFreebuds: Connecting to device…"))
        else:
            self.setToolTip("OpenFreebuds")

        await self.menu.on_core_event(event, state)

        # Update battery percentage icons if enabled
        if state == IOpenFreebuds.STATE_CONNECTED:
            battery = await self.ofb.get_property("battery")
            if battery:
                await self._update_battery_icons(battery)
        else:
            # Hide battery icons when disconnected
            await self._hide_battery_icons()

    async def _get_tooltip_text(self, event: OfbCoreEvent):
        """
        Create tooltip text for tray icon
        """
        if event.is_changed("battery") or event.kind_match(OfbEventKind.DEVICE_CHANGED) or self._last_tooltip == "":
            device_name, _ = await self.ofb.get_device_tags()
            battery = await self.ofb.get_property("battery", "global", "--")
            self._last_tooltip = f"{device_name}: {battery}%"

        return self._last_tooltip

    async def _update_loop(self):
        """
        Background task that will subscribe to core event bus and watch
        for changes to perform tray UI update when something changes.
        """

        async with qt_error_handler("OfbTrayIcon_EventLoop", self.ctx):
            member_id = await self.ofb.subscribe()
            log.info(f"Tray update loop started, member_id={member_id}")

            try:
                while True:
                    kind, *args = await self.ofb.wait_for_event(member_id)
                    event = OfbCoreEvent(kind, *args)

                    if event.kind_match(OfbEventKind.QT_BRING_SETTINGS_UP):
                        self.ctx.main_window.show()
                        self.ctx.main_window.activateWindow()

                    if event.kind_match(OfbEventKind.STATE_CHANGED) and args[0] == IOpenFreebuds.STATE_DESTROYED:
                        raise OfbServerDeadError("Server going to exit")

                    if event.kind_in([
                        OfbEventKind.STATE_CHANGED,
                        OfbEventKind.QT_SETTINGS_CHANGED,
                        OfbEventKind.PROPERTY_CHANGED,
                    ]):
                        await self._update_ui(event)
            except asyncio.CancelledError:
                await self.ofb.unsubscribe(member_id)
            except OfbServerDeadError:
                log.info("Server is dead, exiting now…")
                self.ui_update_task = None
                await self.ctx.exit(1)

    async def _update_battery_icons(self, battery: dict):
        """Update battery percentage tray icons based on config settings"""
        theme = self.config.get_tray_icon_theme()

        # Left earbud
        if self.config.get("ui", "tray_show_left_battery", False) and "left" in battery:
            if self.battery_left_icon is None:
                self.battery_left_icon = QSystemTrayIcon(None)
            icon = create_battery_percentage_icon(theme, battery["left"])
            self.battery_left_icon.setIcon(QIcon(ImageQt.toqpixmap(icon)))
            self.battery_left_icon.setToolTip(f"Left: {battery['left']}%")
            self.battery_left_icon.show()
        elif self.battery_left_icon is not None:
            self.battery_left_icon.hide()

        # Right earbud
        if self.config.get("ui", "tray_show_right_battery", False) and "right" in battery:
            if self.battery_right_icon is None:
                self.battery_right_icon = QSystemTrayIcon(None)
            icon = create_battery_percentage_icon(theme, battery["right"])
            self.battery_right_icon.setIcon(QIcon(ImageQt.toqpixmap(icon)))
            self.battery_right_icon.setToolTip(f"Right: {battery['right']}%")
            self.battery_right_icon.show()
        elif self.battery_right_icon is not None:
            self.battery_right_icon.hide()

        # Case
        if self.config.get("ui", "tray_show_case_battery", False) and "case" in battery:
            if self.battery_case_icon is None:
                self.battery_case_icon = QSystemTrayIcon(None)
            icon = create_battery_percentage_icon(theme, battery["case"])
            self.battery_case_icon.setIcon(QIcon(ImageQt.toqpixmap(icon)))
            self.battery_case_icon.setToolTip(f"Case: {battery['case']}%")
            self.battery_case_icon.show()
        elif self.battery_case_icon is not None:
            self.battery_case_icon.hide()

    async def _hide_battery_icons(self):
        """Hide all battery percentage icons"""
        if self.battery_left_icon is not None:
            self.battery_left_icon.hide()
        if self.battery_right_icon is not None:
            self.battery_right_icon.hide()
        if self.battery_case_icon is not None:
            self.battery_case_icon.hide()
