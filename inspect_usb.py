import serial.tools.list_ports

def inspect_ports():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        print(f"Device: {p.device}")
        print(f"  Name: {p.name}")
        print(f"  Description: {p.description}")
        print(f"  HWID: {p.hwid}")
        print(f"  VID: {p.vid}")
        print(f"  PID: {p.pid}")
        print(f"  Serial Number: {p.serial_number}")
        print(f"  Manufacturer: {p.manufacturer}")
        print(f"  Product: {p.product}")
        print("-" * 20)

if __name__ == "__main__":
    inspect_ports()
