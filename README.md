# CMW500 LAN Query Application

Python application to communicate with a Rohde & Schwarz CMW500 via LAN and query the instrument's identification string.

## Requirements

- Python 3.6+
- Network access to the CMW500

## Usage

```bash
python cmw500_query.py <CMW500_IP_ADDRESS>
```

### Options

- `-p, --port`: SCPI port (default: 5025)
- `-t, --timeout`: Connection timeout in seconds (default: 5.0)

### Examples

```bash
# Query instrument using default port
python cmw500_query.py 192.168.1.100

# Query with custom port and timeout
python cmw500_query.py 192.168.1.100 -p 5025 -t 10
```

## Expected Output

```
Instrument ID: Rohde&Schwarz,CMW500,1234567890,3.8.10
```

The identification string format follows the SCPI standard:
`<Manufacturer>,<Model>,<Serial Number>,<Firmware Version>`
