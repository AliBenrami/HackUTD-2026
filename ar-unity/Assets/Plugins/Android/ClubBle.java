package com.golfar.clubble;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanFilter;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.Context;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelUuid;
import android.os.SystemClock;
import android.util.Log;

import java.util.Collections;
import java.util.UUID;

public final class ClubBle {
    private static final UUID SERVICE = UUID.fromString("6f4c0001-5a1e-4b3d-9c8a-1e2f3a4b5c6d");
    private static final UUID STREAM = UUID.fromString("6f4c0002-5a1e-4b3d-9c8a-1e2f3a4b5c6d");
    private static final UUID CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    private static final long FRESH_MS = 160;
    private static final long STREAM_TIMEOUT_MS = 3000;
    private static final long SETUP_TIMEOUT_MS = 12000;
    private static final long DISCOVERY_TIMEOUT_MS = 35000;
    private static final int MAX_RETRIES = 3;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Context context;
    private final ClubFrames frames = new ClubFrames();
    private final Object samples = new Object();
    private final ClubFrames.Sample acceptSample = this::acceptSample;
    private BluetoothLeScanner scanner;
    private ScanCallback scan;
    private BluetoothGatt gatt;
    private volatile String status = "Club disconnected";
    private final Runnable timeout = () -> retry(scan != null ? "Club not found" : status + " timed out");
    private final Runnable reconnect = this::start;
    private final Runnable streamCheck = this::checkStream;
    private volatile boolean subscribed;
    private volatile boolean active;
    private int retries;
    private float gx, gy, gz, angleX, angleY, angleZ;
    private float integratedSeconds;
    private int deviceTime;
    private long sampleAt;
    private long reportAt;
    private int frameCount, clockResets, maxDeviceGap;
    private float peakRate;

    public ClubBle(Context context) {
        this.context = context.getApplicationContext();
    }

    public void connect() {
        handler.post(() -> {
            retries = 0;
            start();
        });
    }

    public void disconnect() {
        handler.post(() -> close("Club disconnected"));
    }

    public String status() {
        if (subscribed)
            return hasFreshSample() ? "Club gyro live" : "Club connected · waiting for gyro";
        return status;
    }

    private boolean hasFreshSample() {
        synchronized (samples) {
            return subscribed && sampleAt > 0 && SystemClock.elapsedRealtime() - sampleAt <= FRESH_MS;
        }
    }

    public float[] motion() {
        synchronized (samples) {
            if (!subscribed || sampleAt == 0 || SystemClock.elapsedRealtime() - sampleAt > FRESH_MS)
                return null;
            return new float[] { gx, gy, gz, angleX, angleY, angleZ, integratedSeconds };
        }
    }

    public boolean isActive() {
        return active;
    }

    private void setStatus(String message) {
        status = message;
        Log.i("GolfARClub", message);
    }

    private void start() {
        close("Searching for club · power it on", true);
        try {
            BluetoothManager manager = context.getSystemService(BluetoothManager.class);
            BluetoothAdapter adapter = manager == null ? null : manager.getAdapter();
            scanner = adapter == null || !adapter.isEnabled() ? null : adapter.getBluetoothLeScanner();
            if (scanner == null) {
                close("Enable Bluetooth on the Quest");
                return;
            }
            scan = new ScanCallback() {
                @Override public void onScanResult(int type, ScanResult result) {
                    handler.post(() -> found(this, result.getDevice()));
                }

                @Override public void onScanFailed(int error) {
                    handler.post(() -> {
                        if (scan == this)
                            retry("Bluetooth scan failed (" + error + ")");
                    });
                }
            };
            ScanFilter filter = new ScanFilter.Builder().setServiceUuid(new ParcelUuid(SERVICE)).build();
            ScanSettings settings = new ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build();
            scanner.startScan(Collections.singletonList(filter), settings, scan);
            handler.postDelayed(timeout, SETUP_TIMEOUT_MS);
        } catch (SecurityException error) {
            close("Allow Nearby devices to connect");
        }
    }

    private void found(ScanCallback callback, BluetoothDevice device) {
        if (scan != callback)
            return;
        stopScan();
        setupStage("Connecting to club", SETUP_TIMEOUT_MS);
        try {
            gatt = device.connectGatt(context, false, callbacks, BluetoothDevice.TRANSPORT_LE,
                BluetoothDevice.PHY_LE_1M_MASK, handler);
            if (gatt == null)
                retry("Could not connect to club");
        } catch (SecurityException error) {
            close("Allow Nearby devices to connect");
        }
    }

    private final BluetoothGattCallback callbacks = new BluetoothGattCallback() {
        @Override public void onConnectionStateChange(BluetoothGatt connection, int result, int state) {
            if (connection != gatt)
                return;
            if (result != BluetoothGatt.GATT_SUCCESS || state == BluetoothProfile.STATE_DISCONNECTED) {
                retry("Club link lost (GATT " + result + ")");
                return;
            }
            // V1 frames can span notifications at the default ATT MTU.
            if (state == BluetoothProfile.STATE_CONNECTED)
                discover(connection);
        }

        @Override public void onServicesDiscovered(BluetoothGatt connection, int result) {
            if (connection != gatt)
                return;
            BluetoothGattService service = connection.getService(SERVICE);
            BluetoothGattCharacteristic stream = service == null ? null : service.getCharacteristic(STREAM);
            BluetoothGattDescriptor descriptor = stream == null ? null : stream.getDescriptor(CCCD);
            if (result != BluetoothGatt.GATT_SUCCESS || stream == null) {
                if (result == BluetoothGatt.GATT_SUCCESS)
                    close("Club motion stream missing");
                else
                    retry("Club service discovery failed (" + result + ")");
                return;
            }
            if (descriptor == null) {
                close("Update club firmware for BLE");
                return;
            }
            try {
                setupStage("Subscribing to club motion", SETUP_TIMEOUT_MS);
                descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                if (!connection.setCharacteristicNotification(stream, true) || !connection.writeDescriptor(descriptor))
                    retry("Could not subscribe to club");
            } catch (SecurityException error) {
                close("Allow Nearby devices to connect");
            }
        }

        @Override public void onDescriptorWrite(BluetoothGatt connection, BluetoothGattDescriptor descriptor, int result) {
            if (connection != gatt || !CCCD.equals(descriptor.getUuid()))
                return;
            if (result != BluetoothGatt.GATT_SUCCESS) {
                retry("Club subscription failed (" + result + ")");
                return;
            }
            handler.removeCallbacks(timeout);
            setStatus("Subscribed · waiting for gyro");
            subscribed = true;
            try {
                connection.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH);
                // Negotiate only after setup, so a missing MTU callback cannot block play.
                connection.requestMtu(185);
            } catch (SecurityException error) {
                close("Allow Nearby devices to connect");
                return;
            }
            handler.postDelayed(streamCheck, 1000);
        }

        @Override public void onMtuChanged(BluetoothGatt connection, int mtu, int result) {
            if (connection == gatt)
                Log.i("GolfARClub", "ATT MTU " + mtu + " (status " + result + ")");
        }

        // Android 12L uses the legacy overload. Android 13+ provides an immutable value.
        @Override public void onCharacteristicChanged(BluetoothGatt connection, BluetoothGattCharacteristic stream) {
            if (Build.VERSION.SDK_INT < 33)
                receive(connection, stream, stream.getValue());
        }

        @Override public void onCharacteristicChanged(BluetoothGatt connection, BluetoothGattCharacteristic stream, byte[] value) {
            receive(connection, stream, value);
        }
    };

    private void discover(BluetoothGatt connection) {
        setupStage("Discovering club services", DISCOVERY_TIMEOUT_MS);
        try {
            if (!connection.discoverServices())
                retry("Could not discover club motion");
        } catch (SecurityException error) {
            close("Allow Nearby devices to connect");
        }
    }

    private void setupStage(String message, long timeoutMs) {
        setStatus(message);
        handler.removeCallbacks(timeout);
        handler.postDelayed(timeout, timeoutMs);
    }

    private void checkStream() {
        if (!subscribed)
            return;
        long last;
        float seconds;
        synchronized (samples) {
            last = sampleAt;
            seconds = integratedSeconds;
        }
        if (last > 0 && SystemClock.elapsedRealtime() - last > STREAM_TIMEOUT_MS) {
            retry("Club gyro stream stopped");
            return;
        }
        if (last > 0 && seconds >= 3)
            retries = 0;
        handler.postDelayed(streamCheck, 1000);
    }

    private void retry(String reason) {
        Log.w("GolfARClub", reason);
        if (retries == MAX_RETRIES) {
            close(reason + " · try Connect club");
            return;
        }
        long delay = 1500L << retries++;
        close("Club link interrupted · reconnecting", true);
        handler.postDelayed(reconnect, delay);
    }

    private void receive(BluetoothGatt connection, BluetoothGattCharacteristic stream, byte[] value) {
        if (connection == gatt && STREAM.equals(stream.getUuid()) && value != null)
            frames.feed(value, acceptSample);
    }

    private void acceptSample(float x, float y, float z, int timeMs) {
        long now = SystemClock.elapsedRealtime();
        synchronized (samples) {
            // Device time keeps batched notifications from changing swing amplitude.
            if (sampleAt == 0)
                Log.i("GolfARClub", "Gyro samples live");
            int elapsed = timeMs - deviceTime;
            frameCount++;
            maxDeviceGap = Math.max(maxDeviceGap, sampleAt > 0 ? elapsed : 0);
            peakRate = Math.max(peakRate, x * x + y * y + z * z);
            if (sampleAt > 0 && elapsed > 0 && elapsed <= 50 && now - sampleAt <= FRESH_MS) {
                float halfSeconds = elapsed * .0005f;
                angleX += (gx + x) * halfSeconds;
                angleY += (gy + y) * halfSeconds;
                angleZ += (gz + z) * halfSeconds;
                integratedSeconds += elapsed * .001f;
            } else if (sampleAt > 0 && elapsed != 0) {
                // Force a fresh address when integration cannot bridge a missing interval.
                angleX = angleY = angleZ = integratedSeconds = 0;
                clockResets++;
            }
            gx = x;
            gy = y;
            gz = z;
            deviceTime = timeMs;
            sampleAt = now;
            if (now - reportAt >= 4000) {
                if (reportAt != 0 && (clockResets > 0 || peakRate >= 25))
                    Log.d("GolfARClub", "Gyro frames=" + frameCount + ", max device gap=" + maxDeviceGap
                        + " ms, integration resets=" + clockResets + ", peak=" + (int)Math.sqrt(peakRate) + " deg/s");
                reportAt = now;
                frameCount = clockResets = maxDeviceGap = 0;
                peakRate = 0;
            }
        }
    }

    private void stopScan() {
        ScanCallback callback = scan;
        scan = null;
        if (scanner != null && callback != null) {
            try {
                scanner.stopScan(callback);
            } catch (SecurityException ignored) {
                // Permissions can be revoked while scanning.
            }
        }
        scanner = null;
    }

    private void close(String message) {
        close(message, false);
    }

    private void close(String message, boolean keepActive) {
        handler.removeCallbacks(timeout);
        handler.removeCallbacks(reconnect);
        handler.removeCallbacks(streamCheck);
        stopScan();
        BluetoothGatt old = gatt;
        gatt = null;
        if (old != null) {
            try {
                old.disconnect();
            } catch (SecurityException ignored) {
                // Permissions may have been revoked.
            }
            old.close();
        }
        active = keepActive;
        subscribed = false;
        frames.reset();
        synchronized (samples) {
            sampleAt = 0;
            angleX = angleY = angleZ = 0;
            integratedSeconds = 0;
            reportAt = 0;
            frameCount = clockResets = maxDeviceGap = 0;
            peakRate = 0;
        }
        setStatus(message);
    }
}
