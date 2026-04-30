import a2s
import socket

# Define the server address as a tuple (IP address, Query Port)
# Note: The query port might be different from the connection port.
# If the default game port (e.g., 27015) doesn't work, try nearby ports
# such as 27016 or 27017.
SERVER_ADDRESS = ("server_ip_address", 27015)

try:
    # Query the server for basic information. This automatically includes the ping.
    # The timeout parameter prevents the script from hanging indefinitely if the server is offline.
    info = a2s.info(SERVER_ADDRESS, timeout=5.0)

    # The ping is available in the returned SourceInfo object
    # It is typically returned in seconds as a float, so we multiply by 1000 for milliseconds.
    ping_ms = info.ping * 1000

    print(f"Server Name: {info.server_name}")
    print(f"Ping: {ping_ms:.2f} ms")
    print(f"Players: {info.player_count}/{info.max_players}")

except socket.timeout:
    print(f"Error: Connection to {SERVER_ADDRESS} timed out.")
except Exception as e:
    print(f"An error occurred: {e}")
