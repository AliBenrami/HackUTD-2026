"""Connect to the ESP32 sensor stream and yield decoded readings."""

from __future__ import annotations

import asyncio
import sys
from typing import AsyncIterator

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from host.protocol import DEVICE_NAME, SERVICE_UUID, STREAM_UUID, FrameParser, Reading


class SensorLink:
    """BLE client for the HackUTD sensor frame stream.

    New sensor types show up as UnknownReading until a decoder is registered
    in host.protocol.DECODERS. The connection retries on its own.
    """

    def __init__(self, name: str = DEVICE_NAME, scan_timeout: float = 8.0) -> None:
        self.name = name
        self.scan_timeout = scan_timeout

    def _matches(self, device, adv) -> bool:
        advertised = device.name or getattr(adv, "local_name", None) or ""
        if advertised == self.name:
            return True
        uuids = {item.lower() for item in (adv.service_uuids or [])}
        return SERVICE_UUID.lower() in uuids

    async def readings(self) -> AsyncIterator[Reading]:
        backoff = 1.0
        while True:
            try:
                async for reading in self._session():
                    backoff = 1.0
                    yield reading
            except asyncio.CancelledError:
                # CoreBluetooth delivers disconnect on another thread. If the
                # asyncio loop is already gone, PyObjC aborts the process and
                # macOS shows "Python quit unexpectedly."
                await asyncio.sleep(0.4)
                raise
            except (BleakError, OSError, TimeoutError, asyncio.TimeoutError) as exc:
                print(f"sensor link: {exc}; retrying in {backoff:.0f}s", file=sys.stderr)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 8.0)

    async def _session(self) -> AsyncIterator[Reading]:
        print(f"scanning for {self.name}", file=sys.stderr)
        device = await BleakScanner.find_device_by_filter(self._matches, timeout=self.scan_timeout)
        if device is None:
            raise TimeoutError(f"{self.name} was not advertising")

        raw: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        disconnected = asyncio.Event()
        loop = asyncio.get_running_loop()

        def on_notify(_characteristic, data: bytearray) -> None:
            payload = bytes(data)

            def enqueue() -> None:
                try:
                    raw.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

            try:
                loop.call_soon_threadsafe(enqueue)
            except RuntimeError:
                pass

        def on_disconnect(_client) -> None:
            try:
                loop.call_soon_threadsafe(disconnected.set)
            except RuntimeError:
                pass

        print(f"connecting to {device.address}", file=sys.stderr)
        async with BleakClient(device, disconnected_callback=on_disconnect) as client:
            parser = FrameParser()
            await client.start_notify(STREAM_UUID, on_notify)
            print("subscribed", file=sys.stderr)
            while not disconnected.is_set():
                try:
                    chunk = await asyncio.wait_for(raw.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if not client.is_connected:
                        break
                    continue
                for reading in parser.feed(chunk):
                    yield reading
        raise BleakError("disconnected")
