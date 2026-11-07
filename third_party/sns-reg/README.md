# Qualcomm Sensor Registry Server

Qualcomm Sensor Registry (`SNS_REG`) is a QMI service used by the Snapdragon Sensor Core (SSC) on Qualcomm SoCs such as MSM8996 to get platform-specific sensor data. It is served by the AP, and SSC requests data from it in the form of groups of keys. This server emulates the proprietary sensor daemon used in Android and provides SSC with the data it needs to function.

This sensor registry server reads a registry file from `/etc/sns-reg.d/registry.conf` to obtain values of keys requested by SSC.

### Dependencies
- [qrtr](https://github.com/andersson/qrtr/)

### Compilation and use
To compile:
```
scons
```

After placing the registry file in its place, the server can be run:
```
sns-reg
```
at which point it will publish the sensor registry QMI service and start responding to requests coming from SSC.

## Tools
A generator tool is available which can generate a plain-text registry with key-value pairs from a proprietary format `sns.reg` binary registry, which is commonly found in `/persist/sensors/sns.reg` in Android. This tool is useful when a device doesn't ship with a working uncompiled registry, which can sometimes be found in `/system/etc/sensors/*.conf`

Key groups are mapped by monitoring QMI messages between the proprietary sensor daemon and SSC, as well as brute-forcing `sensors.qti`, which is used in Android to generate `sns.reg`. To make sure the group mapping stays valid to the QMI messages intercepted, a validator tool is available to check the sizes of mapped groups.

### Compilation
```
scons tools
```
`sns-reg-generator` and `sns-reg-validator` will be built.
