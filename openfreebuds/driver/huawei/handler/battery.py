import asyncio
import json
from typing import Optional

from openfreebuds.driver.huawei.constants import CMD_BATTERY_READ, CMD_BATTERY_NOTIFY
from openfreebuds.driver.huawei.driver.generic import OfbDriverHandlerHuawei
from openfreebuds.driver.huawei.package import HuaweiSppPackage
from openfreebuds.utils.logger import create_logger

log = create_logger("OfbHuaweiBatteryHandler")


class OfbHuaweiBatteryHandler(OfbDriverHandlerHuawei):
    """
    Battery read handler
    """

    handler_id = "battery"
    commands = [CMD_BATTERY_READ, CMD_BATTERY_NOTIFY]

    def __init__(self, w_tws: bool = True, periodic_update: bool = False, update_interval: float = 1.0):
        self.w_tws = w_tws
        self.periodic_update = periodic_update
        self.update_interval = update_interval
        self.update_task: Optional[asyncio.Task] = None

    async def on_init(self):
        resp = await self.driver.send_package(HuaweiSppPackage.read_rq(CMD_BATTERY_READ, [1, 2, 3]))
        await self.on_package(resp)

        # Start periodic update task if enabled
        if self.periodic_update:
            self.update_task = asyncio.create_task(self._periodic_update_loop())
            log.info(f"Started periodic battery update (interval={self.update_interval}s)")

    async def on_package(self, package: HuaweiSppPackage):
        out = {}
        if 1 in package.parameters and len(package.parameters[1]) == 1:
            out["global"] = int(package.parameters[1][0])
        if 2 in package.parameters and len(package.parameters[2]) == 3 and self.w_tws:
            level = package.parameters[2]
            out["left"] = int(level[0])
            out["right"] = int(level[1])
            out["case"] = int(level[2])
        if 3 in package.parameters and len(package.parameters[3]) > 0:
            out["is_charging"] = json.dumps(b"\x01" in package.parameters[3])
        await self.driver.put_property("battery", None, out)

    async def request_update(self):
        """Request battery update from device"""
        resp = await self.driver.send_package(HuaweiSppPackage.read_rq(CMD_BATTERY_READ, [1, 2, 3]))
        await self.on_package(resp)

    async def _periodic_update_loop(self):
        """Background task that periodically requests battery updates"""
        try:
            while True:
                await asyncio.sleep(self.update_interval)
                try:
                    await self.request_update()
                except Exception as e:
                    log.debug(f"Periodic battery update failed: {e}")
                    # If driver is stopped, this will fail and we should exit
                    if not self.driver.started:
                        log.info("Driver stopped, ending periodic battery updates")
                        break
        except asyncio.CancelledError:
            log.info("Periodic battery update task cancelled")
        except Exception:
            log.exception("Unexpected error in periodic battery update loop")

    async def cleanup(self):
        """Cleanup handler resources"""
        if self.update_task is not None:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
            self.update_task = None
            log.debug("Battery update task cleaned up")
