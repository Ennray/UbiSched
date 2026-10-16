"""Send one representative old-iS2ROS message to the running bridge."""
import socket

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.settimeout(1.0)
    sock.sendto(b"UBI1|1|1110", ("127.0.0.1", 18765))
    response, _ = sock.recvfrom(128)
print("C++ compatible response:", response.decode("ascii"))
