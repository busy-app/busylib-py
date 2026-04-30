import serial
import time

def probe_device(port):
    print(f"Opening {port}...")
    try:
        with serial.Serial(port, 115200, timeout=1) as ser:
            # Clear input buffer
            ser.reset_input_buffer()
            
            # Send newline to trigger prompt/response
            print("Sending newline...")
            ser.write(b"\r\n")
            
            # Read response
            time.sleep(1)
            response = ser.read_all()
            print(f"Received ({len(response)} bytes):")
            print(response)
            try:
                print("Decoded:", response.decode('utf-8', errors='replace'))
            except:
                pass
            
            # Try sending 'help' to see if it's a shell
            print("Sending 'help'...")
            ser.write(b"help\r\n")
            time.sleep(1)
            response = ser.read_all()
            print(f"Received ({len(response)} bytes):")
            print(response.decode('utf-8', errors='replace'))

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    probe_device("/dev/cu.debug-console")
